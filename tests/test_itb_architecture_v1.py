from __future__ import annotations

import ast
import json
from pathlib import Path

from pipeline.media_properties.interstitial_travel_bureau.artifacts import ARTIFACT_FILES
from tests.itb_helpers import PACKAGE_ROOT, PILOT_ROOT, REPO_ROOT, read_json


LIBRARY_FILES = tuple(PACKAGE_ROOT.glob("*.py"))
CLI_FILES = tuple(REPO_ROOT.glob("tools/itb_*_v1.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_itb_production_namespace_has_no_lena_or_network_imports():
    forbidden_roots = {"socket", "urllib", "http", "requests", "anthropic", "boto3"}
    for path in LIBRARY_FILES + CLI_FILES:
        imports = _imports(path)
        assert not any("lena" in name.lower() for name in imports), path
        assert not ({name.split(".")[0] for name in imports} & forbidden_roots), path
        source = path.read_text(encoding="utf-8")
        assert "os.environ" not in source
        assert "getenv(" not in source


def test_library_dependency_direction_is_acyclic_and_matches_map():
    dependency_map = read_json(PACKAGE_ROOT / "documentation" / "dependency_map_v1.json")
    graph = {item["module"]: item["imports"] for item in dependency_map["libraries"]}
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node: str) -> None:
        assert node not in visiting, f"dependency cycle at {node}"
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            walk(dependency)
        visiting.remove(node)
        visited.add(node)

    for module in graph:
        walk(module)
    assert visited == set(graph)


def test_dependency_map_covers_every_schema_artifact_compiler_and_cli():
    dependency_map = read_json(PACKAGE_ROOT / "documentation" / "dependency_map_v1.json")
    assert {item["artifact_type"] for item in dependency_map["schemas"]} == set(ARTIFACT_FILES)
    assert set(dependency_map["compilers"]) == {
        "compile_world_to_script_context",
        "compile_script_to_visual_context",
        "compile_visual_to_generation_plan",
        "compile_plan_to_request",
    }
    assert len(dependency_map["clis"]) == 4
    assert dependency_map["guarantees"]["authority_graph_acyclic"] is True
    assert dependency_map["guarantees"]["provider_network_access"] is False


def test_nine_generators_share_one_provisional_contract():
    generator_files = {
        path.name
        for path in (PACKAGE_ROOT / "generators").glob("*_V1.md")
        if path.name != "GENERATOR_CONTRACT_V1.md"
    }
    assert len(generator_files) == 9
    for filename in generator_files:
        source = (PACKAGE_ROOT / "generators" / filename).read_text(encoding="utf-8")
        assert "GENERATOR_CONTRACT_V1.md" in source
        assert "Produce only" in source or "provisional JSON" in source


def test_pilot_json_contains_no_machine_specific_absolute_paths():
    for path in PILOT_ROOT.glob("*.json"):
        serialized = json.dumps(read_json(path), ensure_ascii=False)
        assert "C:\\" not in serialized
        assert "/home/" not in serialized


def test_technical_document_is_self_contained_for_handoff():
    document = (PACKAGE_ROOT / "documentation" / "ITB_JSON_CREATIVE_OS_V1.md").read_text(encoding="utf-8")
    for heading in ("Production authority", "Five engines", "Creative Genome", "Authority order", "Schema map", "Canonical JSON and hashes", "Creating a new episode", "Future providers", "Reuse for Lena video later", "Error contract", "Deliberately deferred"):
        assert heading in document
