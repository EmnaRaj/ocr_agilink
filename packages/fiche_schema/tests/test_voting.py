"""Self-consistency voting: majority value per cell + agreement-as-confidence."""

from fiche_schema import merge_extraction, vote_extractions


def _run(ref="10108044", matricule="330", qte=80):
    raw = {
        "header": {
            "ref_produit": {"value": ref, "confidence": 0.5},
            "n_of": {"value": "4473", "confidence": 0.9},
            "qte": {"value": 80, "confidence": 0.9},
        },
        "operations": {
            "0": {
                "matricule_operateur": {"value": matricule, "confidence": 0.5},
                "qte_realisee": {"value": qte, "confidence": 0.5},
            }
        },
    }
    return merge_extraction(raw, model_name="test")


def test_majority_vote_picks_agreed_value():
    # 2 runs read 330, 1 reads 338 -> 330 wins, confidence = 2/3.
    voted = vote_extractions([_run(matricule="330"), _run(matricule="330"), _run(matricule="338")])
    cell = voted.operations[0].matricule_operateur
    assert cell.value == "330"
    assert abs(cell.confidence - 2 / 3) < 0.01
    assert cell.source == "vote"


def test_unanimous_gets_full_confidence():
    voted = vote_extractions([_run(matricule="330")] * 3)
    cell = voted.operations[0].matricule_operateur
    assert cell.value == "330"
    assert cell.confidence == 1.0


def test_header_ref_is_voted():
    # The 10108044 vs 20208044 case: 2 correct reads out-vote 1 misread.
    voted = vote_extractions([_run(ref="10108044"), _run(ref="20208044"), _run(ref="10108044")])
    assert voted.header.ref_produit.value == "10108044"
    assert abs(voted.header.ref_produit.confidence - 2 / 3) < 0.01


def test_blank_cell_gets_zero_confidence():
    # All runs read a blank operator on row 1 -> agreement on "blank" must NOT
    # become high confidence (there is no value to be confident about).
    voted = vote_extractions([_run()] * 3)
    assert voted.operations[1].matricule_operateur.value is None
    assert voted.operations[1].matricule_operateur.confidence == 0.0


def test_single_run_passthrough():
    one = _run()
    assert vote_extractions([one]) is one
