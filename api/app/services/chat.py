"""Knowledge-base assistant over the traceability data.

Rather than brittle text-to-SQL, we assemble the *complete corrected dataset*
(every fiche with its extracted fields, products, operators, controls, serials)
into a compact knowledge base and let the model answer any question grounded in
it — and stream the answer token by token.

For large datasets this would move to retrieval (embed + fetch the relevant
fiches); at the current volume the whole base fits in context, which is the
most reliable option.
"""

from collections.abc import Iterator

from openai import OpenAI
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..config import settings
from ..models import Fiche, Operator, Tool, WorkOrder

_MAX_FICHES = 80  # most-recent fiches included in full


def _client() -> OpenAI:
    return OpenAI(base_url=settings.vllm_base_url, api_key=settings.vllm_api_key or "EMPTY")


def _fv(field: object) -> object:
    return (field or {}).get("value") if isinstance(field, dict) else None


def knowledge_base(db: Session) -> str:
    lines = ["BASE DE CONNAISSANCES — Système de traçabilité (Fiches Suiveuses) Agilink", ""]

    operators = db.scalars(select(Operator)).all()
    if operators:
        lines.append(
            "Opérateurs (matricule): "
            + ", ".join(f"{o.matricule}" + (f"={o.nom}" if o.nom else "") for o in operators)
        )
    tools = db.scalars(select(Tool)).all()
    if tools:
        lines.append("Outillages référencés: " + ", ".join(t.code_outillage for t in tools))

    total = db.scalar(select(func.count()).select_from(Fiche)) or 0
    lines.append(f"\nNombre total de fiches: {total}\n")

    fiches = db.scalars(
        select(Fiche)
        .options(joinedload(Fiche.work_order).joinedload(WorkOrder.product))
        .order_by(Fiche.date_creation.desc())
        .limit(_MAX_FICHES)
    ).unique().all()

    for f in fiches:
        ex = f.raw_extraction or {}
        h = ex.get("header") or {}
        hv = lambda k: _fv(h.get(k))  # noqa: E731
        ref = hv("ref_produit") or f.work_order.product.ref_produit
        lines.append(f"=== FICHE #{f.fiche_id} ===")
        lines.append(
            f"Réf. Produit: {ref} | N° OF: {f.work_order.n_of} | "
            f"Quantité: {hv('qte') or f.work_order.quantite} | Statut: {f.statut.value} | "
            f"Scannée le: {f.date_creation:%d/%m/%Y %H:%M}"
        )
        if hv("annotation_serie"):
            lines.append(f"Annotation série: {hv('annotation_serie')}")

        for o in ex.get("operations") or []:
            ov = lambda k: _fv(o.get(k))  # noqa: E731
            date = (o.get("date_op") or {}).get("raw_text") or ""
            if ov("matricule_operateur") or ov("applicable") is not None or date or ov("qte_realisee") is not None:
                lines.append(
                    f"  - Opération P{o.get('partie')} «{o.get('nom_operation')}»: "
                    f"applicable={ov('applicable')}, date={date}, qté={ov('qte_realisee')}, "
                    f"début={str(ov('heure_debut') or '')[:5]}, fin={str(ov('heure_fin') or '')[:5]}, "
                    f"outillage={ov('outillage')}, matricule={ov('matricule_operateur')}"
                )
        for c in ex.get("controls") or []:
            res = _fv(c.get("resultat"))
            verdict = "Conforme" if res is True else ("Non conforme" if res is False else "non renseigné")
            lines.append(
                f"  - Contrôle «{c.get('nom_operation')}»: résultat={verdict}, "
                f"matricule={_fv(c.get('matricule_operateur'))}"
            )
        serials = [_fv(it.get("numero_serie")) for it in (ex.get("items") or [])]
        serials = [s for s in serials if s]
        if serials:
            lines.append(f"  - Numéros de série: {', '.join(map(str, serials))}")
        lines.append("")

    return "\n".join(lines)


_SYSTEM = (
    "Tu es l'assistant intelligent du système de traçabilité industriel Agilink. "
    "Tu réponds aux questions des utilisateurs en te basant UNIQUEMENT sur la base de "
    "connaissances ci-dessous, qui contient toutes les fiches suiveuses scannées et leurs "
    "données extraites. Réponds en français, de façon claire, précise et professionnelle. "
    "Donne les chiffres et références exacts. Si une information ne figure pas dans la base, "
    "dis-le clairement plutôt que d'inventer. Pour les listes/comptages, sois exhaustif. "
    "Réponds en texte clair et naturel, SANS symboles de formatage markdown (n'utilise jamais "
    "** ni * ni #) ; pour une liste, utilise des tirets simples.\n\n"
    "=== DÉBUT DE LA BASE DE CONNAISSANCES ===\n{kb}\n=== FIN DE LA BASE DE CONNAISSANCES ==="
)


def stream_answer(question: str, history: list[dict], db: Session) -> Iterator[str]:
    """Yield the answer token by token, grounded in the full knowledge base."""
    kb = knowledge_base(db)
    messages = [{"role": "system", "content": _SYSTEM.format(kb=kb)}]
    for h in (history or [])[-8:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"][:1500]})
    messages.append({"role": "user", "content": question})

    stream = _client().chat.completions.create(
        model=settings.chat_model,
        temperature=0.2,
        max_tokens=900,
        stream=True,
        messages=messages,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta
