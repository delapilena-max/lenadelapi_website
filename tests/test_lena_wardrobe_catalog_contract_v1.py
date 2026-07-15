from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "pipeline" / "prompt_banks" / "lena" / "lena_wardrobe_catalog_v1.json"


def _load_catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8-sig"))


def _outfit_map() -> dict[str, dict]:
    return {item["outfit_id"]: item for item in _load_catalog()["outfits"]}


def test_catalog_has_current_style_doctrine_and_public_underwear_guardrail() -> None:
    catalog = _load_catalog()
    wardrobe_rule = catalog["wardrobe_rule"].lower()
    doctrine = catalog["style_doctrine"].lower()

    assert "model-like" in wardrobe_rule
    assert "businesslike" in wardrobe_rule
    assert "common sense first" in doctrine
    assert "underwear replacing fashion" in doctrine
    assert "corset-style fashion tops" in doctrine


def test_public_and_going_out_outfits_keep_known_rejections_and_explicit_underlayers() -> None:
    outfits = _outfit_map()

    assert outfits["wc_p033"]["status"] == "rejected"
    assert "bra-as-outerwear" in outfits["wc_p033"]["notes"].lower()
    assert outfits["wc_p078"]["status"] == "rejected"
    assert "do not use in production" in outfits["wc_p078"]["notes"].lower()

    for outfit_id in ("wc_p024", "wc_p025", "wc_p026", "wc_p038"):
        prompt = outfits[outfit_id]["prompt"].lower()
        assert "opaque" in prompt
        assert "full-length" in prompt or "fully covers" in prompt
        assert "bralette" not in prompt
        assert "bikini" not in prompt


def test_boundary_fashion_tops_and_apartment_midriff_rules_stay_explicit() -> None:
    outfits = _outfit_map()

    wc_p081 = outfits["wc_p081"]
    assert wc_p081["style_lane"] == "going_out"
    assert "fashion top" in wc_p081["prompt"].lower()
    assert "not undergarment" in wc_p081["notes"].lower()

    wc_p087 = outfits["wc_p087"]
    assert wc_p087["style_lane"] == "street"
    assert "full torso coverage" in wc_p087["prompt"].lower()
    assert "random crop" in wc_p087["notes"].lower()

    wc_p091 = outfits["wc_p091"]
    assert wc_p091["style_lane"] == "cozy"
    assert "intentional casual midriff" in wc_p091["prompt"].lower()
    assert "at-home casualwear can show intentional midriff" in wc_p091["notes"].lower()
