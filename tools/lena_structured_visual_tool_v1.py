from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


SUPPORTED_IMAGE_MEDIA_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "JPG": "image/jpeg",
    "WEBP": "image/webp",
}


@dataclass(frozen=True)
class StructuredVisualImage:
    path: Path
    sha256: str
    role: str


class StructuredVisualToolError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _image_media_type(path: Path) -> str:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image_format = str(image.format or "").upper()
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise StructuredVisualToolError("image_unreadable", f"image is unreadable: {path}: {exc}") from exc
    if image_format not in SUPPORTED_IMAGE_MEDIA_TYPES:
        raise StructuredVisualToolError("unsupported_media", f"unsupported image format {image_format!r}: {path}")
    return SUPPORTED_IMAGE_MEDIA_TYPES[image_format]


def _read_bound_image_bytes(path: Path, expected_sha256: str) -> bytes:
    image_bytes = path.read_bytes()
    import hashlib

    actual_sha = hashlib.sha256(image_bytes).hexdigest()
    if actual_sha != expected_sha256:
        raise StructuredVisualToolError(
            "image_hash_mismatch",
            f"image bytes changed after validation and before visual upload: {path}",
        )
    return image_bytes


def call_anthropic_structured_visual_tool(
    *,
    images: list[StructuredVisualImage],
    system_prompt: str,
    user_text: str,
    tool_name: str,
    tool_schema: dict[str, Any],
    provider: str,
    model: str,
    timeout_seconds: float,
    max_tokens: int,
) -> Any:
    """Perform one structured Anthropic visual-tool call and return the raw tool payload."""

    if provider != "anthropic":
        raise StructuredVisualToolError("provider_unavailable", f"unsupported provider {provider!r}")
    if not isinstance(model, str) or not model.strip():
        raise StructuredVisualToolError("provider_unavailable", "model must be a non-empty string")
    if timeout_seconds <= 0:
        raise StructuredVisualToolError("provider_unavailable", "timeout_seconds must be positive")
    import anthropic  # type: ignore[import-not-found]
    try:
        import httpx
    except ImportError:  # pragma: no cover - CI minimal dependency set
        httpx = None  # type: ignore[assignment]

    if not isinstance(images, list) or not images:
        raise StructuredVisualToolError("provider_unavailable", "at least one structured visual image is required")
    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    for index, image in enumerate(images, start=1):
        if not isinstance(image, StructuredVisualImage):
            raise StructuredVisualToolError("provider_unavailable", "structured visual images must be StructuredVisualImage objects")
        media_type = _image_media_type(image.path)
        image_bytes = _read_bound_image_bytes(image.path, image.sha256)
        content.append(
            {
                "type": "text",
                "text": f"structured_visual_image_role: {image.role}; structured_visual_image_index: {index}",
            }
        )
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                },
            }
        )

    client = anthropic.Anthropic(max_retries=0)
    timeout_errors = tuple(
        cls for cls in (
            getattr(anthropic, "APITimeoutError", None),
            getattr(httpx, "TimeoutException", None) if httpx is not None else None,
        )
        if isinstance(cls, type)
    )
    rate_limit_errors = tuple(
        cls for cls in (
            getattr(anthropic, "RateLimitError", None),
        )
        if isinstance(cls, type)
    )
    overloaded_errors = tuple(
        cls for cls in (
            getattr(anthropic, "OverloadedError", None),
        )
        if isinstance(cls, type)
    )
    auth_errors = tuple(
        cls for cls in (
            getattr(anthropic, "AuthenticationError", None),
            getattr(anthropic, "PermissionDeniedError", None),
            getattr(anthropic, "WorkloadIdentityError", None),
        )
        if isinstance(cls, type)
    )
    bad_request_errors = tuple(
        cls for cls in (
            getattr(anthropic, "BadRequestError", None),
        )
        if isinstance(cls, type)
    )
    unavailable_errors = tuple(
        cls for cls in (
            getattr(anthropic, "APIConnectionError", None),
            getattr(anthropic, "InternalServerError", None),
            getattr(anthropic, "ConflictError", None),
            getattr(anthropic, "NotFoundError", None),
            getattr(anthropic, "RequestTooLargeError", None),
            getattr(anthropic, "UnprocessableEntityError", None),
            getattr(anthropic, "APIResponseValidationError", None),
        )
        if isinstance(cls, type)
    )
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=[{
                "name": tool_name,
                "description": "Return structured observations only.",
                "input_schema": tool_schema,
            }],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": content}],
            timeout=timeout_seconds,
        )
    except timeout_errors as exc:  # pragma: no cover - exercised via tests
        raise StructuredVisualToolError("provider_timeout", str(exc)) from exc
    except rate_limit_errors as exc:  # pragma: no cover - exercised via tests
        raise StructuredVisualToolError("provider_rate_limit", str(exc)) from exc
    except overloaded_errors as exc:  # pragma: no cover - exercised via tests
        raise StructuredVisualToolError("provider_overloaded", str(exc)) from exc
    except auth_errors as exc:  # pragma: no cover - exercised via tests
        raise StructuredVisualToolError("provider_unavailable", str(exc)) from exc
    except bad_request_errors as exc:  # pragma: no cover - exercised via tests
        raise StructuredVisualToolError("provider_unavailable", str(exc)) from exc
    except getattr(anthropic, "APIStatusError", tuple()) as exc:  # pragma: no cover - exercised via tests
        status = getattr(exc, "status_code", None)
        if status == 429:
            raise StructuredVisualToolError("provider_rate_limit", str(exc)) from exc
        raise StructuredVisualToolError("provider_status_error", str(exc)) from exc
    except unavailable_errors as exc:  # pragma: no cover - exercised via tests
        raise StructuredVisualToolError("provider_unavailable", str(exc)) from exc

    blocks = [
        block
        for block in getattr(response, "content", [])
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name
    ]
    if len(blocks) != 1:
        raise StructuredVisualToolError(
            "malformed_provider_payload",
            "visual provider did not return exactly one structured tool block",
        )
    return blocks[0].input
