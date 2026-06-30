"""
Lena Kling Payload Builder -- Dry Run v1

Reads a content packet JSON (from lena_build_content_packet_dryrun_v1)
and builds a Kling /v1/images/omni-image payload JSON using the correct
Lena character binding:
  fromElementId + elementVersion + approved CDN image_list

Safe: no API call, no generation, no upload, no publish,
no queue, no schedule, no .env reads or writes.
"""
import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("C:/projects/ai/content_bot")
sys.path.insert(0, str(ROOT))

from pipeline.prompting.lena_prompt_brain import (
    build_negative_prompt_for_catalog,
    NEGATIVE_PROMPT,
    format_catalog_wardrobe_override,
    format_style_override,
    pick_style,
    pick_style_production,
)

# ── Lena character binding (no secrets) ───────────────────────────────
LENA_ELEMENT_ID = "u_313006264506046"
LENA_CDN_REFS = [
    (
        "https://s15-kling.klingai.com/kimg/"
        "EMXN1y8qTgoGdXBsb2FkEg55bGFiLXN0dW50LXNncBo0"
        "YWlfcG9ydGFsLzE3ODIyNTY0MDQvenRyN1dOVG5QUy9h"
        "bmNlZC1pbWFnZV9fMjNfLmpwZw.origin"
        "?x-kcdn-pid=112372"
    ),
    (
        "https://s15-kling.klingai.com/kimg/"
        "EMXN1y8qTgoGdXBsb2FkEg55bGFiLXN0dW50LXNncBo0"
        "YWlfcG9ydGFsLzE3ODI0MzQ5ODQvYjI1OUNRYzdrbS8w"
        "MjYtMDYtMjVfMTQxNzQ0LnBuZw.origin"
        "?x-kcdn-pid=112372"
    ),
    (
        "https://s15-kling.klingai.com/kimg/"
        "EMXN1y8qQgoGdXBsb2FkEg55bGFiLXN0dW50LXNncBoo"
        "YWlfcG9ydGFsLzE3ODI0MzM0NjUvNWoxMkZwd3hCOS9r"
        "aW9vLnBuZw.origin"
        "?x-kcdn-pid=112372"
    ),
]

# ── Guard lists ────────────────────────────────────────────────────────
# IDs of retired or wrong elements that must never appear in a payload
BLOCKED_IDS = [
    "313794609092321",
    "313524913093322",
    "314409553525527",
    "314410301504207",
]
# Strings that indicate a wrong payload path or approach
BLOCKED_TERMS = [
    "Goodtest1",
    "element_list",
    "/v1/images/generations",
    "image_reference_intensity",
    "face_reference_intensity",
    ".env.txt",
]
# All must be present (case-insensitive) in the final prompt
MASTER_IDENTITY_CHECKS = [
    "Identity is fixed",
    "Do not slim",
    "petite",
    "hourglass",
    "Do not reinterpret",
    "full natural lifted bust",
    "slim-thick",
    "narrow-hipped",
    "defined waist",
    "wide hips",
]

# ── Paths ──────────────────────────────────────────────────────────────
PACKET_BASE = ROOT / "pipeline/strategy/lena/content_packets"
OUTPUT_BASE = ROOT / "pipeline/strategy/lena/kling_payloads"
WARDROBE_CATALOG = (
    ROOT
    / "pipeline/prompt_banks/lena/lena_wardrobe_catalog_v1.json"
)


def locate_packet(recipe_id: str, date: str) -> Path:
    fname = f"lena_content_packet_dryrun_{date}_{recipe_id}.json"
    p = PACKET_BASE / date / fname
    if not p.is_file():
        raise SystemExit(f"[ABORT] Packet not found: {p}")
    return p


def load_packet(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_packet_gates(packet: dict) -> None:
    checks = {
        "dry_run is True": (
            packet.get("dry_run") is True
        ),
        "provider_call_enabled is False": (
            packet.get("provider_call_enabled") is False
        ),
        "generation_call_performed is False": (
            packet.get("generation_call_performed") is False
        ),
        "publishing_approval is not_approved": (
            packet.get("publishing_approval") == "not_approved"
        ),
    }
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise SystemExit(
            f"[ABORT] Packet gate failures: {failed}"
        )


def rng_for_packet(date: str, recipe_id: str) -> random.Random:
    seed_str = f"{date}:{recipe_id}:kling_payload_v1"
    seed_int = int(
        hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16
    )
    return random.Random(seed_int)


def load_catalog() -> dict:
    with open(WARDROBE_CATALOG, encoding="utf-8") as f:
        return json.load(f)


def select_catalog_outfit(
    catalog: dict,
    outfit_id: str,
    allow_high_risk: bool,
    allow_untested_dryrun: bool = False,
) -> dict:
    outfit = next(
        (o for o in catalog["outfits"] if o["outfit_id"] == outfit_id),
        None,
    )
    if outfit is None:
        raise SystemExit(
            f"[ABORT] wardrobe_outfit_id '{outfit_id}' not in catalog"
        )
    if outfit["status"] == "rejected":
        raise SystemExit(
            f"[ABORT] outfit '{outfit_id}' status=rejected — cannot use"
        )
    if outfit["status"] == "high_risk" and not allow_high_risk:
        raise SystemExit(
            f"[ABORT] outfit '{outfit_id}' is high_risk but "
            "wardrobe_allow_high_risk is false"
        )
    if outfit["status"] == "untested":
        if not allow_untested_dryrun:
            raise SystemExit(
                f"[ABORT] outfit '{outfit_id}' status=untested -- "
                "only approved outfits allowed in v1"
            )
        print(
            f"[DRY-RUN-CATALOG] untested gate bypassed for "
            f"'{outfit_id}' -- dry-run catalog validation only; "
            "catalog status unchanged"
        )
    return outfit


def build_final_prompt(
    base: str, style: dict
) -> tuple[str, str]:
    wardrobe = format_style_override(style)
    combined = f"{base} {wardrobe}".strip()
    if len(combined) > 2499:
        combined = combined[:2499]
    return combined, wardrobe


def fit_prompt_parts(parts: list[str], max_chars: int = 2499) -> str:
    current = ""
    for raw_part in parts:
        part = (raw_part or "").strip()
        if not part:
            continue
        candidate = f"{current} {part}".strip() if current else part
        if len(candidate) <= max_chars:
            current = candidate
    return current


def check_master_identity(prompt: str) -> bool:
    lp = prompt.lower()
    return all(c.lower() in lp for c in MASTER_IDENTITY_CHECKS)


def check_blocked(payload_json: str) -> list:
    return [
        t for t in (BLOCKED_TERMS + BLOCKED_IDS)
        if t in payload_json
    ]


def assemble_payload(prompt: str, negative_prompt: str = NEGATIVE_PROMPT) -> dict:
    return {
        "model_name": "kling-v3-omni",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "fromElementId": LENA_ELEMENT_ID,
        "arguments": [
            {
                "name": "elementVersion",
                "value": json.dumps([
                    {
                        "id": LENA_ELEMENT_ID,
                        "name": "Lena",
                        "type": "IMAGE",
                    }
                ]),
            }
        ],
        "image_list": [{"image": u} for u in LENA_CDN_REFS],
        "aspect_ratio": "9:16",
        "resolution": "2k",
        "n": 1,
    }


def build_envelope(
    packet: dict,
    payload: dict,
    style: dict,
    source_path: Path,
) -> dict:
    payload_json = json.dumps(payload)
    blocked = check_blocked(payload_json)
    master_identity_ok = (
        check_master_identity(payload["prompt"])
        or check_master_identity(packet.get("compact_kling_prompt_preview", ""))
    )
    return {
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "api_call_made": False,
        "publishing_approval": "not_approved",
        "source_packet_path": str(source_path),
        "source_packet_id": packet["packet_id"],
        "source_recipe_id": packet["recipe_id"],
        "generated_date": packet["generated_date"],
        "prompt_chars": len(payload["prompt"]),
        "wardrobe_style_used": (
            {
                "source": "catalog_v1",
                "outfit_id": style["outfit_id"],
                "name": style["name"],
                "status": style["status"],
                "risk_tags": style["risk_tags"],
                "style_lane": style["style_lane"],
            }
            if style.get("_source") == "catalog_v1"
            else {
                "source": "style_bank",
                "category": style["category"],
                "outfit": style["outfit"],
                "hair": style["hair"],
                "makeup": style["makeup"],
                "accessories": style["accessories"],
            }
        ),
        "negative_prompt_present": bool(
            payload.get("negative_prompt")
        ),
        "master_identity_body_present": master_identity_ok,
        "from_element_id_present": (
            "fromElementId" in payload
        ),
        "element_version_present": any(
            a.get("name") == "elementVersion"
            for a in payload.get("arguments", [])
        ),
        "image_list_count": len(payload.get("image_list", [])),
        "blocked_terms_absent": len(blocked) == 0,
        "blocked_terms_found": blocked,
        "scene_logic_contract_present": bool(
            packet.get("scene_logic_contract")
        ),
        "production_proof_mode": packet.get(
            "production_proof_mode", False
        ),
        "realism_iteration_plan": packet.get(
            "realism_iteration_plan", {}
        ),
        "environment_id_used": packet.get("environment_id"),
        "wardrobe_outfit_id_used": packet.get("wardrobe_outfit_id"),
        "payload": payload,
    }


def save_envelope(
    envelope: dict, date: str, recipe_id: str
) -> Path:
    out_dir = OUTPUT_BASE / date
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"kling_payload_dryrun_{date}_{recipe_id}.json"
    fpath = out_dir / fname
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, ensure_ascii=True)
    return fpath


def print_summary(
    envelope: dict,
    source_path: Path,
    output_path: Path,
) -> None:
    payload = envelope["payload"]
    eid = payload["fromElementId"]
    masked = f"u_...{eid[-6:]}"
    blocked = envelope["blocked_terms_found"]
    style = envelope["wardrobe_style_used"]
    chars = envelope["prompt_chars"]
    all_ok = (
        chars < 2500
        and envelope["master_identity_body_present"]
        and envelope["from_element_id_present"]
        and envelope["element_version_present"]
        and envelope["blocked_terms_absent"]
        and envelope["negative_prompt_present"]
    )
    sep = "=" * 64
    print()
    print(sep)
    print("  LENA KLING PAYLOAD BUILDER v1 -- DRY RUN COMPLETE")
    print(sep)
    print(f"  source packet   : {source_path}")
    print(f"  output payload  : {output_path}")
    print(f"  recipe          : {envelope['source_recipe_id']}")
    print()
    print(f"  prompt chars    : {chars}")
    print(f"  under 2500      : {chars < 2500}")
    print()
    if style.get("source") == "catalog_v1":
        print(f"  wardrobe source : catalog_v1")
        print(f"  outfit_id       : {style['outfit_id']}")
        print(f"  outfit name     : {style['name']}")
        print(f"  status          : {style['status']}")
        print(f"  risk_tags       : {style['risk_tags']}")
        print(f"  style_lane      : {style['style_lane']}")
    else:
        print(f"  wardrobe        : {style['category']}")
        print(f"  outfit          : {style['outfit']}")
        print(f"  hair            : {style['hair']}")
        print(f"  makeup          : {style['makeup']}")
        print(f"  accessories     : {style['accessories']}")
    print()
    print(f"  fromElementId   : {masked}")
    print(f"  elementVersion  : {envelope['element_version_present']}")
    print(f"  image_list ct   : {envelope['image_list_count']}")
    print(f"  neg prompt      : {envelope['negative_prompt_present']}")
    print(
        f"  master identity : "
        f"{envelope['master_identity_body_present']}"
    )
    print(f"  blocked absent  : {envelope['blocked_terms_absent']}")
    if blocked:
        print(f"  BLOCKED FOUND   : {blocked}")
    print(
        "  scene contract  : "
        f"{envelope.get('scene_logic_contract_present', False)}"
    )
    print(
        "  proof mode      : "
        f"{envelope.get('production_proof_mode', False)}"
    )
    plan = envelope.get("realism_iteration_plan", {})
    if plan:
        print(
            "  iteration mode  : "
            f"{plan.get('mode', 'unknown')}"
        )
    print(
        "  outfit used     : "
        f"{envelope.get('wardrobe_outfit_id_used', 'style_bank')}"
    )
    print(
        "  env used        : "
        f"{envelope.get('environment_id_used', 'none')}"
    )
    print()
    print(f"  VALIDATION      : {'PASSED' if all_ok else 'FAILED'}")
    print()
    print("  NO API call.       NO generation.    NO upload.")
    print("  NO publish.        NO queue.          NO schedule.")
    print(sep)
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lena Kling Payload Builder v1 -- dry run"
    )
    parser.add_argument(
        "--packet",
        help="Path to an existing content packet JSON",
    )
    parser.add_argument(
        "--recipe",
        help="Recipe ID (e.g. hcr_001) — locates today's packet",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Date YYYY-MM-DD for --recipe lookup (default: today UTC)",
    )
    args = parser.parse_args()

    if args.packet:
        packet_path = Path(args.packet)
        if not packet_path.is_file():
            raise SystemExit(f"[ABORT] Not found: {packet_path}")
    elif args.recipe:
        date = args.date or datetime.now(timezone.utc).strftime(
            "%Y-%m-%d"
        )
        packet_path = locate_packet(args.recipe, date)
    else:
        parser.error("Provide --packet <path> or --recipe <id>")
        return 1

    packet = load_packet(packet_path)
    validate_packet_gates(packet)

    recipe_id = packet["recipe_id"]
    date = packet["generated_date"]

    outfit_id = packet.get("wardrobe_outfit_id")
    allow_hr = packet.get("wardrobe_allow_high_risk", False)
    allow_untested_dryrun = (
        packet.get("dry_run") is True
        and packet.get("provider_call_enabled") is False
        and packet.get("generation_call_performed") is False
    )

    if outfit_id:
        catalog = load_catalog()
        catalog_outfit = select_catalog_outfit(
            catalog,
            outfit_id,
            allow_hr,
            allow_untested_dryrun=allow_untested_dryrun,
        )
        wardrobe_text = format_catalog_wardrobe_override(catalog_outfit)
        base = packet["compact_kling_prompt_preview"]
        env_ctx = (packet.get("environment_context", "") or "").strip()
        prompt_parts = [base, wardrobe_text]
        if env_ctx:
            prompt_parts.append(env_ctx)
        final_prompt = fit_prompt_parts(prompt_parts, max_chars=2499)
        if wardrobe_text not in final_prompt:
            raise SystemExit(
                "[ABORT] wardrobe override did not fit into final Kling prompt; "
                "increase reserved headroom before live use."
            )
        if env_ctx and env_ctx not in final_prompt:
            raise SystemExit(
                "[ABORT] environment context did not fit into final Kling "
                "prompt; increase reserved headroom before live use."
            )
        style = {
            "_source": "catalog_v1",
            "outfit_id": catalog_outfit["outfit_id"],
            "name": catalog_outfit["name"],
            "status": catalog_outfit["status"],
            "risk_tags": catalog_outfit["risk_tags"],
            "style_lane": catalog_outfit["style_lane"],
        }
        negative_prompt = build_negative_prompt_for_catalog(catalog_outfit)
    else:
        rng = rng_for_packet(date, recipe_id)
        style = pick_style_production(rng)
        wardrobe_text = format_style_override(style)
        prompt_parts = [packet["compact_kling_prompt_preview"], wardrobe_text]
        final_prompt = fit_prompt_parts(prompt_parts, max_chars=2499)
        if wardrobe_text not in final_prompt:
            raise SystemExit(
                "[ABORT] style-bank wardrobe override did not fit into final "
                "Kling prompt; reduce the compact packet budget before live use."
            )
        negative_prompt = NEGATIVE_PROMPT

    if not (
        check_master_identity(final_prompt)
        or check_master_identity(packet.get("compact_kling_prompt_preview", ""))
    ):
        raise SystemExit(
            "[ABORT] Master identity/body rule not detected in prompt. "
            "Packet may be missing LENA_IDENTITY_BRIEF updates."
        )

    payload = assemble_payload(final_prompt, negative_prompt=negative_prompt)
    envelope = build_envelope(packet, payload, style, packet_path)

    if envelope["blocked_terms_found"]:
        raise SystemExit(
            "[ABORT] Blocked terms in payload: "
            f"{envelope['blocked_terms_found']}"
        )

    output_path = save_envelope(envelope, date, recipe_id)
    print_summary(envelope, packet_path, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
