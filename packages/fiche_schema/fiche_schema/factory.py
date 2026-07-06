"""Build a blank FicheExtraction skeleton from the canonical operation lists.

Used to scaffold the VLM's expected output shape and in tests, so the row
order/count for a fiche can never drift from the template.
"""

from __future__ import annotations

import re
from datetime import date, time

from .extraction import (
    ControlRow,
    ExtractedField,
    ExtractionMeta,
    FicheExtraction,
    FicheHeader,
    Item,
    Methode,
    OperationRow,
    Partie,
    TypeControle,
)
from .operations import CONTROLE_ROWS, PARTIE_1_OPERATIONS, PARTIE_2_OPERATIONS
from .validation import weighted_overall_confidence

_CONTROLE_TYPES = (
    TypeControle.electrique,
    TypeControle.final,
    TypeControle.correspondance_serie,
)


def _blank_field() -> ExtractedField:
    return ExtractedField()


def blank_operation_rows() -> list[OperationRow]:
    rows: list[OperationRow] = []
    for ordre, nom in enumerate(PARTIE_1_OPERATIONS, start=1):
        rows.append(
            OperationRow(
                partie=Partie.p1,
                nom_operation=nom,
                ordre=ordre,
                applicable=_blank_field(),
                date_op=_blank_field(),
                date_fin=_blank_field(),
                heure_debut=_blank_field(),
                heure_fin=_blank_field(),
                qte_realisee=_blank_field(),
                outillage=_blank_field(),
                matricule_operateur=_blank_field(),
            )
        )
    for ordre, nom in enumerate(PARTIE_2_OPERATIONS, start=1):
        rows.append(
            OperationRow(
                partie=Partie.p2,
                nom_operation=nom,
                ordre=ordre,
                applicable=_blank_field(),
                date_op=_blank_field(),
                date_fin=_blank_field(),
                heure_debut=_blank_field(),
                heure_fin=_blank_field(),
                qte_realisee=_blank_field(),
                outillage=_blank_field(),
                matricule_operateur=_blank_field(),
            )
        )
    return rows


def blank_control_rows() -> list[ControlRow]:
    rows: list[ControlRow] = []
    for ordre, (nom, type_controle) in enumerate(
        zip(CONTROLE_ROWS, _CONTROLE_TYPES), start=1
    ):
        rows.append(
            ControlRow(
                partie=Partie.controle,
                nom_operation=nom,
                ordre=ordre,
                type_controle=type_controle,
                applicable=_blank_field(),
                date_op=_blank_field(),
                date_fin=_blank_field(),
                heure_debut=_blank_field(),
                heure_fin=_blank_field(),
                qte_realisee=_blank_field(),
                outillage=_blank_field(),
                matricule_operateur=_blank_field(),
            )
        )
    return rows


def blank_fiche_extraction(model_name: str) -> FicheExtraction:
    return FicheExtraction(
        header=FicheHeader(
            ref_produit=_blank_field(),
            n_of=_blank_field(),
            qte=_blank_field(),
        ),
        operations=blank_operation_rows(),
        controls=blank_control_rows(),
        items=[],
        meta=ExtractionMeta(model_name=model_name),
    )


# --- Merging a VLM's raw JSON response onto the canonical skeleton ---------
#
# The VLM is never asked for operation names/order/partie/type_controle — it
# only fills in the per-row extracted values, in the fixed order given to it
# in the prompt. Building on the blank skeleton means row identity/count can
# never drift from the template regardless of what the model returns.


def _parse_bool(v: object) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "oui", "yes")
    return bool(v)


def _parse_date(v: object) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v).strip())


def _parse_time(v: object) -> time:
    if isinstance(v, time):
        return v
    s = str(v).strip().lower().replace("h", ":").rstrip(":")
    parts = s.split(":")
    hour = parts[0].zfill(2)
    minute = parts[1].zfill(2) if len(parts) > 1 else "00"
    second = parts[2].zfill(2) if len(parts) > 2 else "00"
    return time.fromisoformat(f"{hour}:{minute}:{second}")


def _parse_methode(v: object) -> Methode:
    s = str(v).strip().lower().replace(" ", "_").replace("-", "_")
    return Methode(s)


def _ef(raw_field: object, parser=lambda v: v) -> ExtractedField:
    raw_field = raw_field if isinstance(raw_field, dict) else {}
    raw_value = raw_field.get("value")
    raw_text = raw_field.get("raw_text")
    try:
        confidence = float(raw_field.get("confidence") or 0.0)
    except (ValueError, TypeError):
        confidence = 0.0

    value = None
    if raw_value is not None:
        try:
            value = parser(raw_value)
        except (ValueError, TypeError):
            # A single malformed cell (e.g. two times stacked into one string,
            # "20 pcs" where an int was expected) must NOT abort the whole
            # 25-row sheet. Degrade this one field to null, preserve what the
            # model actually read in raw_text, and drop confidence to 0 so the
            # review UI flags it for a human instead of silently losing it.
            if raw_text is None and not isinstance(raw_value, (dict, list)):
                raw_text = str(raw_value)
            value = None
            confidence = 0.0

    return ExtractedField(
        value=value,
        confidence=confidence,
        raw_text=raw_text,
        source="vlm",
    )


_TABLE_FIELD_PARSERS = {
    "applicable": _parse_bool,
    "date_op": _parse_date,
    "date_fin": _parse_date,
    "heure_debut": _parse_time,
    "heure_fin": _parse_time,
    "qte_realisee": int,
    "outillage": str,
    "matricule_operateur": str,
}


def _normalize_date_raw(text: str | None) -> str | None:
    """Canonicalize a handwritten "day.month" reading to one canonical date form
    — zero-padded with a slash, "DD/MM" — regardless of whether the writer (or
    the model copying it) used ".", "/" or "-". They're the same date, but a
    table mixing separators/padding row to row reads as an error even when every
    cell was individually transcribed correctly. Falls back to the original text
    on anything that doesn't look like two numbers — never raises."""
    if not text:
        return text
    parts = re.split(r"[./-]", text.strip())
    if len(parts) != 2:
        return text
    try:
        day, month = int(parts[0]), int(parts[1])
    except ValueError:
        return text
    return f"{day:02d}/{month:02d}"


def _merge_table_fields(raw_row: object) -> dict:
    raw_row = raw_row if isinstance(raw_row, dict) else {}
    fields = {name: _ef(raw_row.get(name), parser) for name, parser in _TABLE_FIELD_PARSERS.items()}
    for key in ("date_op", "date_fin"):
        fields[key] = fields[key].model_copy(update={"raw_text": _normalize_date_raw(fields[key].raw_text)})
    return fields


def _as_indexed_dict(raw: object) -> dict:
    """Tolerates a plain JSON array too, in case the model ignores the
    keyed-object instruction — treated positionally as a best-effort fallback."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {str(i): row for i, row in enumerate(raw)}
    return {}


def merge_operation_rows(raw_operations: dict) -> list[OperationRow]:
    """`raw_operations` is keyed by stringified row index (e.g. "0", "1", ...).

    Keyed lookup (rather than positional zip) means a row the VLM omitted —
    because it ran out of output budget, or judged it blank/not worth
    repeating — falls back to the blank/zero-confidence row instead of
    silently shifting every later row out of alignment.
    """
    raw_operations = _as_indexed_dict(raw_operations)
    blanks = blank_operation_rows()
    return [
        blank.model_copy(update=_merge_table_fields(raw_operations.get(str(i))))
        for i, blank in enumerate(blanks)
    ]


def merge_control_rows(raw_controls: dict) -> list[ControlRow]:
    """See `merge_operation_rows` — same keyed-by-index tolerance."""
    raw_controls = _as_indexed_dict(raw_controls)
    blanks = blank_control_rows()
    rows = []
    for i, blank in enumerate(blanks):
        raw_row = raw_controls.get(str(i))
        raw_row = raw_row if isinstance(raw_row, dict) else {}
        fields = _merge_table_fields(raw_row)
        fields["methode"] = _ef(raw_row.get("methode"), _parse_methode)
        fields["resultat"] = _ef(raw_row.get("resultat"), _parse_bool)
        rows.append(blank.model_copy(update=fields))
    return rows


def merge_header(raw_header: object) -> FicheHeader:
    raw_header = raw_header if isinstance(raw_header, dict) else {}
    return FicheHeader(
        ref_produit=_ef(raw_header.get("ref_produit"), str),
        n_of=_ef(raw_header.get("n_of"), str),
        qte=_ef(raw_header.get("qte"), int),
        annotation_serie=_ef(raw_header.get("annotation_serie"), str),
    )


def merge_items(raw_items: object) -> list[Item]:
    raw_items = raw_items if isinstance(raw_items, list) else []
    return [Item(numero_serie=_ef(raw_item.get("numero_serie") if isinstance(raw_item, dict) else None, str)) for raw_item in raw_items]


def merge_extraction(raw: dict, model_name: str, processing_ms: int | None = None) -> FicheExtraction:
    """Merge a VLM's raw JSON response onto the canonical skeleton.

    Operation/control rows are looked up by index, so a row the model omitted
    just comes out blank/zero-confidence rather than misaligning the rest.
    Individual malformed cell values degrade to null (with the raw text kept
    for review) instead of aborting the sheet — see `_ef`. A structurally
    broken response (e.g. a non-object where an object is required) can still
    raise; callers should surface that as an extraction failure.
    """
    header = merge_header(raw.get("header"))
    operations = merge_operation_rows(raw.get("operations") or {})
    controls = merge_control_rows(raw.get("controls") or {})
    items = merge_items(raw.get("items"))

    extraction = FicheExtraction(
        header=header,
        operations=operations,
        controls=controls,
        items=items,
        meta=ExtractionMeta(
            model_name=model_name,
            overall_confidence=0.0,
            processing_ms=processing_ms,
        ),
    )
    # Importance-weighted over the header + filled cells (not a flat average
    # diluted by blank rows) — see validation.weighted_overall_confidence.
    extraction.meta.overall_confidence = weighted_overall_confidence(extraction)
    return extraction
