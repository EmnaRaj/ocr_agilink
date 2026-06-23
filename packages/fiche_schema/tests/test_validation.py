"""Tests for the deterministic validation + weighted-confidence layer.

Run: `python -m tests.test_validation` from the package root.
"""

from fiche_schema import merge_extraction, validate_extraction, weighted_overall_confidence


def _fiche(raw):
    return merge_extraction(raw, model_name="test")


def test_weighted_confidence_not_diluted_by_blanks():
    # One strong header + one filled op; the other 24 blank rows must NOT drag
    # the score down to a flat average.
    raw = {
        "header": {
            "ref_produit": {"value": "10106751", "confidence": 1.0},
            "n_of": {"value": "1554", "confidence": 1.0},
            "qte": {"value": 20, "confidence": 1.0},
        },
        "operations": {"0": {"matricule_operateur": {"value": "330", "confidence": 1.0}}},
    }
    assert weighted_overall_confidence(_fiche(raw)) > 0.95  # flat avg would be ~0.1


def test_missing_critical_field_tanks_confidence():
    raw = {"header": {"qte": {"value": 20, "confidence": 1.0}}}  # no ref / no OF
    # ref_produit + n_of count as 0 (weights 5 + 4), so the score must be low.
    assert weighted_overall_confidence(_fiche(raw)) < 0.4


def test_detects_non_numeric_ref():
    raw = {"header": {"ref_produit": {"value": "10A0B751", "confidence": 1.0},
                      "n_of": {"value": "1554", "confidence": 1.0}}}
    codes = {i.code for i in validate_extraction(_fiche(raw))}
    assert "ref_non_numerique" in codes


def test_detects_qty_overflow_column_swap():
    # A matricule (330) wrongly placed in the qty column → impossible vs OF qte 20.
    raw = {
        "header": {"ref_produit": {"value": "10106751", "confidence": 1.0},
                   "n_of": {"value": "1554", "confidence": 1.0},
                   "qte": {"value": 20, "confidence": 1.0}},
        "operations": {"0": {"qte_realisee": {"value": 330, "confidence": 1.0}}},
    }
    codes = {i.code for i in validate_extraction(_fiche(raw))}
    assert "qte_superieure" in codes


def test_detects_time_incoherence():
    raw = {
        "header": {"ref_produit": {"value": "10106751", "confidence": 1.0},
                   "n_of": {"value": "1554", "confidence": 1.0}},
        "operations": {"0": {
            "heure_debut": {"value": "15:30", "confidence": 1.0},
            "heure_fin": {"value": "09:30", "confidence": 1.0},
        }},
    }
    codes = {i.code for i in validate_extraction(_fiche(raw))}
    assert "heure_incoherente" in codes


def test_unknown_matricule_flagged_against_referential():
    raw = {
        "header": {"ref_produit": {"value": "10106751", "confidence": 1.0},
                   "n_of": {"value": "1554", "confidence": 1.0}},
        "operations": {"0": {"matricule_operateur": {"value": "999", "confidence": 1.0}}},
    }
    issues = validate_extraction(_fiche(raw), known_matricules={"330", "164"})
    assert any(i.code == "matricule_inconnu" for i in issues)


def test_clean_fiche_has_no_issues():
    raw = {
        "header": {"ref_produit": {"value": "10106751", "confidence": 1.0},
                   "n_of": {"value": "1554", "confidence": 1.0},
                   "qte": {"value": 20, "confidence": 1.0}},
        "operations": {"0": {
            "applicable": {"value": True, "confidence": 1.0},
            "qte_realisee": {"value": 20, "confidence": 1.0},
            "heure_debut": {"value": "09:00", "confidence": 1.0},
            "heure_fin": {"value": "10:15", "confidence": 1.0},
            "matricule_operateur": {"value": "330", "confidence": 1.0},
        }},
    }
    assert validate_extraction(_fiche(raw), known_matricules={"330"}) == []


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    _run()
