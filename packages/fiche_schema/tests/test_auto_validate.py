"""The rule-based auto-validate gate: clean sheet -> yes, any flag -> no."""

from fiche_schema import is_auto_validatable, merge_extraction, validate_extraction


def _fiche(ref="10106751", n_of="1554", qte=20, matricule="330", qte_realisee=20, conf=1.0):
    raw = {
        "header": {
            "ref_produit": {"value": ref, "confidence": conf},
            "n_of": {"value": n_of, "confidence": conf},
            "qte": {"value": qte, "confidence": conf},
        },
        "operations": {
            "0": {
                "applicable": {"value": True, "confidence": conf},
                "qte_realisee": {"value": qte_realisee, "confidence": conf},
                "heure_debut": {"value": "09:00", "confidence": conf},
                "heure_fin": {"value": "10:15", "confidence": conf},
                "matricule_operateur": {"value": matricule, "confidence": conf},
            }
        },
        "meta": {"model_name": "test", "overall_confidence": conf},
    }
    ex = merge_extraction(raw, model_name="test")
    ex.meta.overall_confidence = conf
    return ex


def _issues(ex, known={"330"}):
    return validate_extraction(ex, known_matricules=known)


def test_clean_sheet_auto_validates():
    ex = _fiche()
    assert is_auto_validatable(ex, _issues(ex)) is True


def test_clean_new_operator_does_not_block():
    # A well-formed matricule not in the (learned) roster and NOT resembling any
    # known one is treated as a new operator, not a misread — Agilink onboards
    # people continuously, so blocking it would refuse correct sheets. It
    # self-registers once it recurs. 999 shares no digit with known {"330"}.
    ex = _fiche(matricule="999")
    assert is_auto_validatable(ex, _issues(ex)) is True


def test_misread_lookalike_matricule_blocks():
    # A one-off that looks exactly like a common known operator with a single
    # confused digit (380 vs known 330, 3<->8 is a handwriting confusion pair)
    # is the fingerprint of a real misread -> hard block (routed to human).
    ex = _fiche(matricule="380")
    assert is_auto_validatable(ex, _issues(ex)) is False


def test_qty_mismatch_blocks():
    ex = _fiche(qte=20, qte_realisee=200)  # strong misread signal -> block
    assert is_auto_validatable(ex, _issues(ex)) is False


def test_missing_ref_blocks():
    ex = _fiche(ref=None)  # ERROR-level -> structurally unusable -> blocks
    assert is_auto_validatable(ex, _issues(ex)) is False


def test_low_confidence_floor_blocks_even_when_clean():
    ex = _fiche(conf=0.5)  # clean rules, but below the secondary confidence floor
    assert not _issues(ex)
    assert is_auto_validatable(ex, _issues(ex), min_confidence=0.9) is False
