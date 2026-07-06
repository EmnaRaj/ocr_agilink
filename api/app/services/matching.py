from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from fiche_schema import split_matricules, systematic_misreads

from ..models import Operator, OperationRow, Product, Tool, WorkOrder

_FUZZY_THRESHOLD = 0.78  # min similarity to accept a fuzzy tool match

# A matricule seen on at least this many DISTINCT sheets is trusted as a real
# operator (below → treated as a possible new hire / misread, not yet trusted).
_ROSTER_MIN_SHEETS = 2


def known_matricules(db: Session, min_sheets: int = _ROSTER_MIN_SHEETS) -> set[str]:
    """The operator roster — LEARNED live from the data, never a static list.

    Agilink adds and removes operators over time, so the referential can't be a
    hand-maintained allow-list. Instead we derive it from the extractions
    themselves: a matricule that recurs on `min_sheets`+ DISTINCT sheets is a
    real operator (a random misread almost never recurs *identically* on
    separate sheets, whereas a real operator recurs constantly). This grows the
    moment a new operator's second sheet arrives and drops them when they stop
    appearing — zero maintenance, fully dynamic. Unioned with any operator a
    human has explicitly confirmed (the `Operator` table), so a reviewer-blessed
    value counts even when seen only once.
    """
    sheets: dict[str, set[int]] = {}
    for fiche_id, mat in (
        db.query(OperationRow.fiche_id, OperationRow.matricule)
        .filter(OperationRow.matricule.isnot(None))
    ):
        for part in split_matricules(mat):
            if part.isdigit() and 2 <= len(part) <= 3:  # a real matricule is 2-3 digits
                sheets.setdefault(part, set()).add(fiche_id)
    counts = {m: len(ids) for m, ids in sheets.items()}
    # A value that recurs only because a common operator is misread the same way
    # every time (e.g. 164 -> 161) must never be trusted as its own operator —
    # otherwise the misread self-validates and stops being flagged.
    misreads = systematic_misreads(counts, min_sheets)
    learned = {m for m, n in counts.items() if n >= min_sheets}
    confirmed = {m for (m,) in db.query(Operator.matricule).all()}
    roster = (learned | confirmed) - misreads
    # A real matricule is 2-3 digits; drop any malformed entry (e.g. a 4-digit
    # 1142 that a cold-start auto-validation registered) so it never counts as a
    # trusted operator.
    return {m for m in roster if m.isdigit() and 2 <= len(m) <= 3}


def find_or_create_product(db: Session, ref_produit: str) -> Product:
    product = db.query(Product).filter_by(ref_produit=ref_produit).first()
    if product is None:
        product = Product(ref_produit=ref_produit)
        db.add(product)
        db.flush()
    return product


def find_or_create_work_order(
    db: Session, n_of: str, product: Product, quantite: int | None
) -> WorkOrder:
    work_order = db.query(WorkOrder).filter_by(n_of=n_of).first()
    if work_order is None:
        work_order = WorkOrder(n_of=n_of, product=product, quantite=quantite)
        db.add(work_order)
        db.flush()
    return work_order


def match_operator(db: Session, matricule: str | None) -> Operator | None:
    if not matricule:
        return None
    return db.query(Operator).filter_by(matricule=matricule.strip()).first()


def find_or_create_operator(db: Session, matricule: str | None) -> Operator | None:
    """Look up an operator by matricule, registering it if this is the first
    time it's been seen.

    Only call this for a HUMAN-CONFIRMED reading (fiche validation) — the
    known-operator registry that `validate_extraction`'s `matricule_inconnu`
    check relies on is meant to grow organically from real, validated PDF
    extractions, not from a manually-supplied list. Auto-creating from a
    still-unverified VLM read would let misreads (the exact failure mode the
    check exists to catch) pollute the registry it's checked against.

    Still rejects an implausible-format value (not 2-4 digits) even on a
    validated fiche — e.g. "338/347" (an unseparated two-operator handoff a
    human validated without splitting first) must never become a trusted
    registry entry, or it pollutes the very check meant to catch exactly
    that kind of malformed read.
    """
    if not matricule:
        return None
    matricule = matricule.strip()
    digits = "".join(c for c in matricule if c.isdigit())
    if not (2 <= len(digits) <= 4) or len(digits) != len(matricule):
        return None
    operator = db.query(Operator).filter_by(matricule=matricule).first()
    if operator is None:
        operator = Operator(matricule=matricule)
        db.add(operator)
        db.flush()
    return operator


def match_tool(db: Session, outillage_text: str | None) -> Tool | None:
    """Match free-text "outillage" to the controlled tools list.

    First an exact substring match, then a fuzzy fallback so OCR noise like
    "Pince B" still resolves to "Pince 8". Unmatched text is preserved
    losslessly in Fiche.raw_extraction; the validation gate flags a non-match
    for review rather than silently dropping it.
    """
    if not outillage_text:
        return None
    text = outillage_text.strip().lower()
    tools = db.query(Tool).all()

    for tool in tools:
        if tool.code_outillage.lower() in text or (tool.libelle or "").lower() in text:
            return tool

    best, best_score = None, 0.0
    for tool in tools:
        for cand in (tool.code_outillage, tool.libelle or ""):
            if not cand:
                continue
            score = SequenceMatcher(None, text, cand.lower()).ratio()
            if score > best_score:
                best, best_score = tool, score
    return best if best_score >= _FUZZY_THRESHOLD else None
