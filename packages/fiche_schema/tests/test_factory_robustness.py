"""Regression tests for the VLM-response merge layer's robustness.

These guard the two failure modes that took down real extractions during
Phase 1 testing against the live fixture:

  1. A single malformed cell value (e.g. two times stacked into one string)
     used to raise and abort the whole 25-row sheet with an HTTP 502.
  2. Single-digit hours like "9:30" used to crash `time.fromisoformat`.

Dependency-free: run with `python -m tests.test_factory_robustness` from the
package root, or under pytest if/when it's added to the dev deps.
"""

from datetime import time

from fiche_schema.factory import _ef, _parse_time, merge_extraction


def test_parse_time_accepts_single_digit_and_h_forms():
    assert _parse_time("9:30") == time(9, 30)
    assert _parse_time("9h30") == time(9, 30)
    assert _parse_time("15h") == time(15, 0)
    assert _parse_time("14:30") == time(14, 30)
    assert _parse_time("09:30:00") == time(9, 30)


def test_bad_cell_degrades_instead_of_raising():
    # Two times stacked into one string — must not raise; must null the value
    # but preserve what the model read for human review, at zero confidence.
    field = _ef({"value": "08:06 10:40", "confidence": 0.9}, _parse_time)
    assert field.value is None
    assert field.raw_text == "08:06 10:40"
    assert field.confidence == 0.0


def test_bad_int_cell_degrades():
    field = _ef({"value": "20 pcs", "confidence": 1.0}, int)
    assert field.value is None
    assert field.raw_text == "20 pcs"
    assert field.confidence == 0.0


def test_non_numeric_confidence_degrades_to_zero():
    field = _ef({"value": "330", "confidence": "high"}, str)
    assert field.value == "330"
    assert field.confidence == 0.0


def test_one_bad_cell_does_not_lose_the_other_rows():
    raw = {
        "header": {"ref_produit": {"value": "10106751", "confidence": 1.0}},
        "operations": {
            "0": {"matricule_operateur": {"value": "330", "confidence": 1.0},
                  "heure_fin": {"value": "08:06 10:40", "confidence": 0.5}},
            "1": {"matricule_operateur": {"value": "164", "confidence": 1.0}},
        },
    }
    ex = merge_extraction(raw, model_name="test")
    assert ex.header.ref_produit.value == "10106751"
    assert ex.operations[0].matricule_operateur.value == "330"
    assert ex.operations[0].heure_fin.value is None  # degraded, not fatal
    assert ex.operations[1].matricule_operateur.value == "164"


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    _run()
