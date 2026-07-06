"""Business-intelligence analytics for the dashboard.

Everything here analyses the *content extracted from the fiches* — the
operations, controls, operators, quantities and timings — not file-level
metadata. It reads the unified `operation_rows` table (the single source of
truth) and is scoped to VALIDATED fiches, i.e. the data a human has confirmed,
so the manager is looking at trustworthy figures rather than raw VLM reads.

Four analytical axes (chosen with the manager in mind):
  1. Conformity & defects   — control pass/fail, non-conformities, review load
  2. Operation flow         — coverage and cycle-time bottlenecks per operation
  3. Operator performance   — workload and average cycle time per operator
  4. Quantity & traceability— volumes, serials traced, throughput over time
"""

from collections import Counter, defaultdict
from datetime import time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from fiche_schema import split_matricules

from ..db import get_db
from ..models import Fiche, OperationRow, Partie, StatutFiche, WorkOrder

router = APIRouter(tags=["analytics"])

_CONTROL_LABEL = {
    "controle_electrique": "Contrôle électrique",
    "controle_final": "Contrôle final",
    "correspondance_serie": "Correspondance série",
}


def _mins(t: time | None) -> int | None:
    return t.hour * 60 + t.minute if t is not None else None


def _applied(o: OperationRow) -> bool:
    """An operation counts as 'done' if it's marked applicable or has an operator."""
    return o.applicable is True or bool(o.matricule)


@router.get("/analytics")
def analytics(db: Session = Depends(get_db)) -> dict:
    # Process funnel over ALL fiches (the only file-level figure kept — a manager
    # still needs to see how much data is awaiting review vs. confirmed).
    statut_counts = dict(
        db.execute(select(Fiche.statut, func.count()).group_by(Fiche.statut)).all()
    )
    total_fiches = sum(statut_counts.values())

    fiches = db.scalars(
        select(Fiche)
        .where(Fiche.statut == StatutFiche.valide)
        .options(
            joinedload(Fiche.work_order).joinedload(WorkOrder.product),
            selectinload(Fiche.rows),
            selectinload(Fiche.items),
            selectinload(Fiche.audit_events),
        )
        .order_by(Fiche.date_creation)
    ).unique().all()

    op_total = op_applied = 0
    operators: Counter = Counter()                       # matricule -> applied ops
    operator_minutes: defaultdict[str, list[int]] = defaultdict(list)
    cycle_by_op: defaultdict[str, list[int]] = defaultdict(list)
    coverage_applied: Counter = Counter()                # op name -> applied
    coverage_total: Counter = Counter()                  # op name -> seen
    tools: Counter = Counter()
    timeline: Counter = Counter()                        # DD/MM -> applied ops
    timing_ok = 0

    conformity: Counter = Counter()                      # Conforme / Non conforme / Non renseigné
    control_by_type: defaultdict[str, dict] = defaultdict(lambda: {"ok": 0, "ko": 0, "na": 0})
    nonconf_by_product: Counter = Counter()
    flagged_rows = 0

    products_qty: Counter = Counter()                    # ref -> ordered qty
    serials_by_product: Counter = Counter()
    serials_total = 0
    corrections_total = 0

    for f in fiches:
        ref = f.work_order.product.ref_produit
        products_qty[ref] += int(f.work_order.quantite or 0)
        n_serials = len(f.items)
        serials_total += n_serials
        serials_by_product[ref] += n_serials
        corrections_total += len(f.audit_events)

        for o in f.rows:
            if o.statut_revue is not None and o.statut_revue.value == "a_revoir":
                flagged_rows += 1

            if o.partie == Partie.controle:
                if o.resultat is True:
                    conformity["Conforme"] += 1
                    bucket = "ok"
                elif o.resultat is False:
                    conformity["Non conforme"] += 1
                    nonconf_by_product[ref] += 1
                    bucket = "ko"
                else:
                    conformity["Non renseigné"] += 1
                    bucket = "na"
                label = _CONTROL_LABEL.get(
                    o.type_controle.value if o.type_controle else "", o.nom_operation[:24]
                )
                control_by_type[label][bucket] += 1
                continue

            # --- operations (Partie 1/2) ---
            op_total += 1
            coverage_total[o.nom_operation] += 1
            if _applied(o):
                op_applied += 1
                coverage_applied[o.nom_operation] += 1
                for m in split_matricules(o.matricule):
                    operators[m] += 1
                if o.date_op:
                    timeline[o.date_op.strftime("%d/%m")] += 1
                if o.outillage:
                    tools[o.outillage] += 1
                md, mf = _mins(o.heure_debut), _mins(o.heure_fin)
                if md is not None and mf is not None and o.date_fin is None and mf >= md:
                    cycle_by_op[o.nom_operation].append(mf - md)
                    timing_ok += 1
                    for m in split_matricules(o.matricule):
                        operator_minutes[m].append(mf - md)

    # --- KPIs ---
    conf_ok = conformity.get("Conforme", 0)
    conf_total = conf_ok + conformity.get("Non conforme", 0)
    conformity_pct = round(100 * conf_ok / conf_total) if conf_total else None
    automated = sum(1 for f in fiches if not f.audit_events)
    automation_pct = round(100 * automated / len(fiches)) if fiches else None
    all_durations = [d for ds in cycle_by_op.values() for d in ds]
    cycle_time_minutes = round(sum(all_durations) / len(all_durations), 1) if all_durations else None
    cycle_time_coverage_pct = round(100 * timing_ok / op_applied) if op_applied else 0

    def ranked_cycle(d: dict[str, list[int]]) -> list[dict]:
        return sorted(
            ({"name": k, "avg_minutes": round(sum(v) / len(v), 1), "n": len(v)} for k, v in d.items()),
            key=lambda x: -x["avg_minutes"],
        )

    coverage_by_operation = sorted(
        (
            {
                "name": name,
                "applied": coverage_applied.get(name, 0),
                "total": total,
                "pct": round(100 * coverage_applied.get(name, 0) / total) if total else 0,
            }
            for name, total in coverage_total.items()
        ),
        key=lambda x: -x["applied"],
    )

    return {
        "scope": {"validated": len(fiches), "total_fiches": total_fiches},
        "kpis": {
            "operations_done": op_applied,
            "conformity_pct": conformity_pct,
            "non_conformities": conformity.get("Non conforme", 0),
            "automation_pct": automation_pct,
            "cycle_time_minutes": cycle_time_minutes,
            "cycle_time_coverage_pct": cycle_time_coverage_pct,
            "flagged_rows": flagged_rows,
            "corrections": corrections_total,
            "operators": len(operators),
            "serials": serials_total,
            "products": len([r for r in products_qty if products_qty[r] >= 0]),
        },
        "review_funnel": [
            {"name": "Extrait", "value": statut_counts.get(StatutFiche.extrait, 0)},
            {"name": "En revue", "value": statut_counts.get(StatutFiche.en_revue, 0)},
            {"name": "Validé", "value": statut_counts.get(StatutFiche.valide, 0)},
        ],
        # 1. Conformity & defects
        "conformity": [{"name": k, "value": v} for k, v in conformity.items()],
        "control_results_by_type": [
            {"type": k, "ok": v["ok"], "ko": v["ko"], "na": v["na"]}
            for k, v in control_by_type.items()
        ],
        "non_conformities_by_product": [
            {"ref": k, "count": v} for k, v in nonconf_by_product.most_common(8)
        ],
        # 2. Operation flow & bottlenecks
        "operation_coverage": [
            {"name": "Réalisées", "value": op_applied},
            {"name": "Non renseignées", "value": max(op_total - op_applied, 0)},
        ],
        "coverage_by_operation": coverage_by_operation,
        "cycle_time_by_operation": ranked_cycle(cycle_by_op)[:8],
        # 3. Operator performance
        "operator_workload": [
            {"matricule": k, "operations": v} for k, v in operators.most_common(10)
        ],
        "operator_cycle_time": ranked_cycle(operator_minutes)[:10],
        # 4. Quantity & traceability
        "product_volumes": [{"ref": k, "qty": v} for k, v in products_qty.most_common(8)],
        "serials_by_product": [
            {"ref": k, "serials": v} for k, v in serials_by_product.most_common(8)
        ],
        "timeline": [{"date": k, "operations": v} for k, v in sorted(timeline.items())],
        "top_tools": [{"name": k, "count": v} for k, v in tools.most_common(6)],
    }
