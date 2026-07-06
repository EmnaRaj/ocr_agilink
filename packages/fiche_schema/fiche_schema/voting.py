"""Self-consistency voting over N independent extractions of the SAME sheet.

Hosted VLM inference is non-deterministic: the same image read twice can differ
cell to cell (we measured a single fiche swinging 98% -> 78% purely from
re-sampling). Running the extraction a few times and taking the per-cell
MAJORITY value cancels those random misreads — and the inter-run AGREEMENT
becomes a *calibrated* confidence (how many runs agreed), far more trustworthy
than the model's own self-reported number, which is what the >=98%
auto-validate gate needs.

Voting is positional-safe: every run is merged onto the same fixed 25-operation
/ 3-control skeleton (factory.merge_extraction), so `operations[i]` is the same
row across all runs.
"""

from __future__ import annotations

from collections import Counter

from .extraction import ExtractedField, FicheExtraction, FicheHeader, Item
from .validation import weighted_overall_confidence

_TABLE_FIELDS = (
    "applicable", "date_op", "date_fin", "heure_debut", "heure_fin",
    "qte_realisee", "outillage", "matricule_operateur",
)


def _key(field: ExtractedField) -> tuple:
    """A comparable key for grouping equal readings across runs. Dates carry
    their value in raw_text (the VLM emits value=null), so vote on that."""
    v = field.value
    if v is None:
        rt = (field.raw_text or "").strip().lower()
        return ("raw", rt) if rt else ("blank",)
    if isinstance(v, bool):
        return ("val", v)
    return ("val", str(v).strip().lower())


def _vote(fields: list[ExtractedField]) -> ExtractedField:
    """Pick the value the most runs agree on; confidence = agreement ratio.

    A blank cell all runs agree on gets confidence 0.0 (there is no *value* to be
    confident about — and a blank critical field should not lift the score),
    while a filled cell all runs agree on gets 1.0.
    """
    keys = [_key(f) for f in fields]
    winner, n = Counter(keys).most_common(1)[0]
    agreement = round(n / len(fields), 3)
    # representative field for the winning reading — keep the highest-confidence one
    rep = max((f for f, k in zip(fields, keys) if k == winner), key=lambda f: f.confidence)
    is_blank = winner[0] == "blank"
    return rep.model_copy(update={"confidence": 0.0 if is_blank else agreement, "source": "vote"})


def vote_extractions(runs: list[FicheExtraction]) -> FicheExtraction:
    """Majority-vote N extractions of one sheet into a single voted extraction."""
    if len(runs) == 1:
        return runs[0]
    base = runs[0]  # canonical structure (operation names / partie / ordre / type_controle)

    header = FicheHeader(
        ref_produit=_vote([r.header.ref_produit for r in runs]),
        n_of=_vote([r.header.n_of for r in runs]),
        qte=_vote([r.header.qte for r in runs]),
        annotation_serie=_vote([(r.header.annotation_serie or ExtractedField()) for r in runs]),
    )

    operations = []
    for i, row in enumerate(base.operations):
        upd = {f: _vote([getattr(r.operations[i], f) for r in runs]) for f in _TABLE_FIELDS}
        operations.append(row.model_copy(update=upd))

    controls = []
    for i, row in enumerate(base.controls):
        upd = {f: _vote([getattr(r.controls[i], f) for r in runs]) for f in _TABLE_FIELDS}
        upd["methode"] = _vote([r.controls[i].methode for r in runs])
        upd["resultat"] = _vote([r.controls[i].resultat for r in runs])
        controls.append(row.model_copy(update=upd))

    # Serials: vote per position (best-effort — runs may list them in any order).
    items = []
    for i in range(max(len(r.items) for r in runs)):
        voted = _vote([(r.items[i].numero_serie if i < len(r.items) else ExtractedField()) for r in runs])
        if voted.value or (voted.raw_text and voted.raw_text.strip()):
            items.append(Item(numero_serie=voted))

    ex = FicheExtraction(
        header=header, operations=operations, controls=controls, items=items, meta=base.meta.model_copy()
    )
    ex.meta.overall_confidence = weighted_overall_confidence(ex)
    return ex
