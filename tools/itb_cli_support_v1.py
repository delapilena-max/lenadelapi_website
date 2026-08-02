from __future__ import annotations

import argparse
import json
from typing import Any

from pipeline.media_properties.interstitial_travel_bureau.contracts import (
    ITBContractError,
    Issue,
    structured_failure,
)


class JsonArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, add_help=False, **kwargs)
        self.add_argument("--help", action="store_true", dest="json_help")

    def error(self, message: str) -> None:
        raise ITBContractError(
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
        "report_type": "itb_cli_help_v1",
        "command": command,
        "usage": parser.format_usage().strip(),
        "help_text": parser.format_help(),
    }


def emit(report: dict[str, Any]) -> int:
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("ok") is True else 1


def emit_contract_error(report_type: str, error: ITBContractError) -> int:
    return emit(structured_failure(report_type, error))
