from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from ..models import Operator, Product, Tool, WorkOrder

_FUZZY_THRESHOLD = 0.78  # min similarity to accept a fuzzy tool match


def known_matricules(db: Session) -> set[str]:
    """All operator matricules — the referential the validation layer checks against."""
    return {m for (m,) in db.query(Operator.matricule).all()}


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
