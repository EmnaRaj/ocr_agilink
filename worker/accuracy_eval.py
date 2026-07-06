"""Phase-1 accuracy harness — per-cell extraction accuracy on the validated fiches.

Ground truth = each VALIDATED fiche's raw_extraction (human-corrected). For each,
we re-render its page UPRIGHT (using the stored rotation, so orientation flakiness
doesn't pollute the reading score), re-run the current VLM pipeline, and compare
every cell to the validated value.

Run in the worker container (has both `app.*` and `worker.*`):
    docker compose cp worker/accuracy_eval.py worker:/srv/worker/accuracy_eval.py
    docker compose exec -T worker sh -c 'cd /srv/worker && python accuracy_eval.py'
"""

import os
import re
from collections import defaultdict
from itertools import zip_longest

import pymupdf

from app.db import SessionLocal
from app.models import Fiche, StatutFiche
from app.services import ingest
from app.services.storage import download_scan
from worker.tasks import _get_vlm_client

HEADER_FIELDS = ["ref_produit", "n_of", "qte"]
OP_FIELDS = ["applicable", "date_op", "date_fin", "heure_debut", "heure_fin",
            "qte_realisee", "outillage", "matricule_operateur"]
CTRL_FIELDS = ["resultat", "methode", "matricule_operateur"]


def _norm_value(s: str) -> str:
    s = s.strip().lower()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):      # ISO date  -> M-D (year not on sheet)
        return f"{int(s[5:7])}-{int(s[8:10])}"
    # Day/month written any way ("13.3", "13/03", "13-3") -> canonical "m-d" so a
    # format change (DD.MM -> DD/MM) isn't counted as a misread; only the digits matter.
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})$", s)
    if m:
        return f"{int(m.group(2))}-{int(m.group(1))}"
    if re.match(r"^\d{2}:\d{2}:\d{2}$", s):       # HH:MM:SS  -> HH:MM
        return s[:5]
    return s


def cell_str(field: object) -> str | None:
    """A field's comparable value, or None when effectively blank."""
    if not isinstance(field, dict):
        return None
    v = field.get("value")
    if v is None:
        rt = field.get("raw_text")
        return _norm_value(str(rt)) if rt and str(rt).strip() else None
    if isinstance(v, bool):
        return "oui" if v else "non"
    if isinstance(v, dict):           # methode: nested {value: ...}
        v = v.get("value")
        if v is None:
            return None
    return _norm_value(str(v)) or None


def render_upright(doc: "pymupdf.Document", page_index: int, rotation: int) -> bytes:
    """Render the page the same way the extractor did, applying the stored rotation."""
    page = doc.load_page(page_index)
    page.set_rotation((page.rotation + rotation) % 360)
    zoom = min(5600 / max(page.rect.width, page.rect.height), 5.5)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    return pix.tobytes("jpeg", jpg_quality=95)


def main() -> None:
    db = SessionLocal()
    client = _get_vlm_client()
    # field -> {filled, correct, false_write, examples}
    stats: dict[str, dict] = defaultdict(lambda: {"filled": 0, "correct": 0, "false_write": 0, "examples": []})
    per_fiche = []

    fiches = db.query(Fiche).filter(Fiche.statut == StatutFiche.valide).all()

    print(f"Evaluating {len(fiches)} validated fiches against the current VLM "
          f"({client.__class__.__name__})...\n")

    def compare(field_name: str, gt_field: object, pred_field: object) -> int | None:
        """Returns 1 (correct) / 0 (wrong) for a FILLED gt cell, else None (blank gt)."""
        gt = cell_str(gt_field)
        pred = cell_str(pred_field)
        s = stats[field_name]
        if gt is None:
            if pred is not None:
                s["false_write"] += 1
            return None
        s["filled"] += 1
        if gt == pred:
            s["correct"] += 1
            return 1
        if len(s["examples"]) < 4:
            s["examples"].append((gt, pred))
        return 0

    for f in fiches:
        gt = f.raw_extraction or {}
        if f.scan is None or not (gt.get("operations") or gt.get("header")):
            continue
        try:
            data, _ = download_scan(f.scan.storage_url)
            doc = pymupdf.open(stream=data, filetype="pdf")
            img = render_upright(doc, f.page_index, f.rotation)
            passes = int(os.environ.get("EXTRACT_PASSES", "3"))
            pred = client.extract_voted(img, mime_type="image/jpeg", passes=passes).model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            print(f"  fiche {f.fiche_id}: SKIPPED ({exc})")
            continue

        correct = total = 0
        gh, ph = gt.get("header") or {}, pred.get("header") or {}
        for fld in HEADER_FIELDS:
            r = compare(f"header.{fld}", gh.get(fld), ph.get(fld))
            if r is not None:
                total += 1; correct += r
        for go, po in zip_longest(gt.get("operations") or [], pred.get("operations") or [], fillvalue={}):
            for fld in OP_FIELDS:
                r = compare(f"op.{fld}", go.get(fld), po.get(fld))
                if r is not None:
                    total += 1; correct += r
        for gc, pc in zip_longest(gt.get("controls") or [], pred.get("controls") or [], fillvalue={}):
            for fld in CTRL_FIELDS:
                r = compare(f"ctrl.{fld}", gc.get(fld), pc.get(fld))
                if r is not None:
                    total += 1; correct += r
        for gi, pi in zip_longest(gt.get("items") or [], pred.get("items") or [], fillvalue={}):
            r = compare("item.numero_serie", gi.get("numero_serie"), pi.get("numero_serie"))
            if r is not None:
                total += 1; correct += r

        acc = (100 * correct / total) if total else 0.0
        conf = float((pred.get("meta") or {}).get("overall_confidence") or 0.0)
        ref = ((gh.get("ref_produit") or {}).get("value")) or "?"
        per_fiche.append((f.fiche_id, ref, correct, total, acc, conf))
        print(f"  fiche {f.fiche_id:>4}  {ref:<12}  {correct:>3}/{total:<3} cells  {acc:5.1f}%  conf {conf:.2f}")

    # ---- report ----
    filled = sum(s["filled"] for s in stats.values())
    ok = sum(s["correct"] for s in stats.values())
    fw = sum(s["false_write"] for s in stats.values())
    print("\n" + "=" * 64)
    print(f"OVERALL PER-CELL ACCURACY (filled cells): {100*ok/filled:.1f}%  ({ok}/{filled})"
          if filled else "no filled cells")
    print(f"Hallucinated writes into blank cells: {fw}")
    # Auto-validate gate: how many sheets clear >=98% confidence, and are they
    # actually right? An auto-validated sheet with a wrong cell is the one danger.
    GATE = 0.98
    auto = [pf for pf in per_fiche if pf[5] >= GATE]
    auto_ok = [pf for pf in auto if pf[2] == pf[3]]  # every cell correct
    print(f"AUTO-VALIDATE GATE (voted confidence >= {GATE:.2f}):")
    print(f"  {len(auto)}/{len(per_fiche)} sheets would auto-validate (no human review)")
    print(f"    -> {len(auto_ok)} fully correct, {len(auto) - len(auto_ok)} with >=1 wrong cell (must stay 0)")
    print("=" * 64)
    print(f"\n{'FIELD':<26}{'FILLED':>7}{'CORRECT':>9}{'ACC%':>7}{'FALSE-WR':>10}")
    for name in sorted(stats, key=lambda n: (stats[n]['correct'] / stats[n]['filled']) if stats[n]['filled'] else 1):
        s = stats[name]
        if not s["filled"] and not s["false_write"]:
            continue
        acc = (100 * s["correct"] / s["filled"]) if s["filled"] else float("nan")
        print(f"{name:<26}{s['filled']:>7}{s['correct']:>9}{acc:>7.1f}{s['false_write']:>10}")

    print("\nWORST FIELDS — sample misreads (ground truth -> got):")
    worst = sorted((n for n in stats if stats[n]["examples"]),
                   key=lambda n: stats[n]["correct"] / stats[n]["filled"] if stats[n]["filled"] else 1)
    for name in worst[:8]:
        ex = ", ".join(f"'{g}'->'{p}'" for g, p in stats[name]["examples"])
        print(f"  {name:<24} {ex}")

    db.close()


if __name__ == "__main__":
    main()
