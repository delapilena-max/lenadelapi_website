from __future__ import annotations

import argparse
import json
from typing import Any

from pipeline.media_properties.lena.video.contracts import (
    Issue,
    LenaVideoContractError,
    structured_failure,
    zero_activity_counters,
)


EXIT_SUCCESS = 0
EXIT_CONTRACT_FAILURE = 2
EXIT_FILESYSTEM_FAILURE = 3


class JsonArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, add_help=False, **kwargs)
        self.add_argument("--help", action="store_true", dest="json_help")

    def error(self, message: str) -> None:
        raise LenaVideoContractError(
            Issue(
                code="cli_arguments_invalid",
                stage="cli",
                message="Command arguments do not match the CLI contract.",
                actual=message,
                suggested_correction=self.format_usage().strip(),
            )
        )


def help_report(parser: argparse.ArgumentParser, command: str) -> dict[str, Any]:
    return {
        "ok": True,
        "report_type": "lena_video_cli_help_v1",
        "command": command,
        "usage": parser.format_usage().strip(),
        "help_text": parser.format_help(),
        "counters": zero_activity_counters(),
    }


def emit(report: dict[str, Any], *, exit_code: int = EXIT_SUCCESS) -> int:
    payload = dict(report)
    payload["exit_code"] = exit_code
    print(json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True))
    return exit_code


def emit_contract_error(report_type: str, error: LenaVideoContractError) -> int:
    return emit(
        structured_failure(report_type, error),
        exit_code=EXIT_CONTRACT_FAILURE,
    )


def emit_filesystem_error(report_type: str, error: OSError) -> int:
    return emit(
        structured_failure(
            report_type,
            LenaVideoContractError(
                Issue(
                    code="filesystem_error",
                    stage="filesystem",
                    message="Filesystem operation failed.",
                    actual=str(error),
                )
            ),
        ),
        exit_code=EXIT_FILESYSTEM_FAILURE,
    )
