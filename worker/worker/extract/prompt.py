from fiche_schema import CONTROLE_ROWS, PARTIE_1_OPERATIONS, PARTIE_2_OPERATIONS

_OPERATIONS = PARTIE_1_OPERATIONS + PARTIE_2_OPERATIONS

# Global operation indices for each Partie, so a focused per-section prompt can
# hand the model exactly the index keys that section's crop is responsible for.
P1_INDICES = tuple(range(len(PARTIE_1_OPERATIONS)))
P2_INDICES = tuple(range(len(PARTIE_1_OPERATIONS), len(_OPERATIONS)))


def _numbered(names: tuple[str, ...]) -> str:
    return "\n".join(f"{i}: {name}" for i, name in enumerate(names))


def _numbered_subset(indices: tuple[int, ...]) -> str:
    return "\n".join(f"{i}: {_OPERATIONS[i]}" for i in indices)


# --- Shared building blocks -------------------------------------------------

_INTRO = (
    'You are extracting data from a scanned French paper traceability sheet '
    '("Fiche Suiveuse") used on a cable/harness assembly line.'
)

# Reading rules that apply across the whole sheet. Kept in one place so the
# per-section prompts can't drift apart on the things that bite us (digit
# misreads, fabricated date years, row misalignment).
_DIGIT_NOTE = (
    '- DIGIT FIELDS ARE ALL-NUMERIC. "ref_produit", "n_of", "qte", '
    '"matricule_operateur" and "numero_serie" contain ONLY digits 0-9, never '
    'letters. In this handwriting a "1" can look like "l"/"L" and a crossed '
    'European "7" can look like "f"/"F"/"t" — always transcribe these as the '
    'DIGIT they actually are. Never put a space inside a number '
    '(write the digits joined together, with no spaces between them).'
)
_CONFIDENCE_NOTE = (
    '- "confidence" is YOUR self-estimate of how certain you are about that '
    "exact value given what's legible — do not report high confidence on a "
    "value you are guessing or inferring."
)
_OPERATION_SHAPE = """Each operation/control entry has this shape (all keys present; use null \
value and 0.0 confidence for a blank or illegible cell; "raw_text" is optional \
— include it when "value" is null but you could still read something):
{
  "applicable": {"value": <true|false|null>, "confidence": <0..1>},
  "date_op": {"value": null, "confidence": 0.0, "raw_text": <"DD.MM" you read, or omit>},
  "date_fin": {"value": null, "confidence": 0.0, "raw_text": <"DD.MM" you read, or omit>},
  "heure_debut": {"value": <"HH:MM" or null>, "confidence": <0..1>},
  "heure_fin": {"value": <"HH:MM" or null>, "confidence": <0..1>},
  "qte_realisee": {"value": <integer or null>, "confidence": <0..1>},
  "outillage": {"value": <string or null>, "confidence": <0..1>},
  "matricule_operateur": {"value": <string or null>, "confidence": <0..1>}
}"""

_TABLE_NOTES = f"""Notes on reading the operations table:
- "applicable" is the "Oui/Non" column: true if marked "Oui"/checked, false if \
"Non", null if blank.
- The "Date" and "Qté réalisée" columns are two SEPARATE narrow side-by-side \
columns. The date is day.month only (format DD.MM) with NO year anywhere on \
the sheet; the 1-2 digit number just to its right is the SEPARATE \
quantity, not a year. Never concatenate them, never treat a 1-2 digit number \
as a year. Always set every "date_op"/"date_fin" value to null and put the \
day.month text in "raw_text".
- Time may be written "15h30" or "14:30" — normalize to "HH:MM". A time written \
as just an hour followed by "h" with nothing after it means HH:00 — so "13h" \
is "13:00" (NOT 13:30), "9h" is "09:00". If a date AND time are stacked in the \
"Heure fin" cell, put only the time in "heure_fin".
- HEURE DE FIN: if the "Heure de fin" cell is EMPTY, set "heure_fin" to null. \
NEVER invent an end time, never copy the start time, never put a number from \
another column here.
- "matricule_operateur" is the RIGHTMOST number on the row (the last column). \
"outillage" is the column immediately to its LEFT — it may be a tool name \
("manuel", "Pince…") OR a short number. If the outillage is a number, the \
matricule is still the number FURTHER RIGHT than it. Never put the outillage \
value into the matricule cell, and keep any matricule digits out of outillage.
{_DIGIT_NOTE}
- CRITICAL — ROW IDENTITY: do NOT count rows or guess positions. For each \
filled row, READ the PRINTED operation name on the far left of that row and \
copy it into "operation". The handwriting on a line always belongs to the \
printed label printed on that same line — never to the line above or below. \
The three "Serrage …" rows (raccords arrières / capots / colliers Band'it) \
are different operations; read the full label to tell them apart.
{_CONFIDENCE_NOTE}"""


_OPERATION_FIELDS = """  "applicable": {"value": <true|false|null>, "confidence": <0..1>},
  "date_op": {"value": null, "confidence": 0.0, "raw_text": <"DD.MM" you read, or omit>},
  "heure_debut": {"value": <"HH:MM" or null>, "confidence": <0..1>},
  "heure_fin": {"value": <"HH:MM" or null>, "confidence": <0..1>},
  "qte_realisee": {"value": <integer or null>, "confidence": <0..1>},
  "outillage": {"value": <string or null>, "confidence": <0..1>},
  "matricule_operateur": {"value": <string or null>, "confidence": <0..1>}"""


def build_operations_prompt(indices: tuple[int, ...]) -> str:
    """Label-anchored prompt: the model returns each FILLED row tagged with the
    printed operation name it reads (not a positional index), which we then map
    back to the canonical row. This removes the row-counting that made the model
    collapse blank rows and shift every later row out of alignment.
    """
    names = "\n".join(f"- {_OPERATIONS[i]}" for i in indices)
    return f"""{_INTRO}

This image is a crop of the operations table for one "Partie". Each ROW has a \
PRINTED operation name on the far left, then handwritten columns in this order: \
Applicable (Oui/Non), Date, Qté réalisée, Heure de début, Heure de fin, \
Outillage, Matricule Opérateur.

The printed operation names in this section, top to bottom, are EXACTLY:
{names}

For EVERY row that contains ANY handwriting, return one object with:
- "operation": the printed operation name on the left of that row, copied \
EXACTLY from the list above.
- these field values:
{_OPERATION_FIELDS}

Skip rows that have no handwriting at all. Return ONLY a single JSON object:
{{ "rows": [ {{"operation": "<printed name>", "applicable": {{...}}, ...}}, ... ] }}

{_TABLE_NOTES}
"""


def build_controls_prompt() -> str:
    """Focused prompt for the controls + serial-numbers crop."""
    return f"""{_INTRO}

This image is the crop containing the three control rows and the part serial \
numbers at the bottom of the sheet.

{_OPERATION_SHAPE}
Each "controls" entry additionally has:
{{
  "methode": {{"value": <"manuel"|"banc_de_test"|null>, "confidence": <0..1>}},
  "resultat": {{"value": <true|false|null>, "confidence": <0..1>}}
}}
("methode" only applies to the "Contrôle électrique" row; null for the others.)

Return ONLY a single JSON object of the form:
{{
  "controls": {{ "0": {{...}}, "1": {{...}}, "2": {{...}} }},
  "items": [ {{"numero_serie": {{"value": <string or null>, "confidence": <0..1>}}}}, ... ]
}}

The "controls" index order (index: control label):
{_numbered(CONTROLE_ROWS)}

Notes:
- "resultat" is the pass/fail of the control: true if "Oui"/conforme/checked, \
null if the row is blank (do not invent "Oui" for an unmarked row).
- The "matricule_operateur" for a control row is in the FAR-RIGHT column — \
check there for a handwritten operator number even when the rest of the row \
is just the printed control label/sentence.
- "items" holds the handwritten part serial numbers listed at the bottom; if \
only a range (e.g. "500 -> 512") is written and no individual numbers are \
listed, return an empty "items" array rather than expanding the range.
{_DIGIT_NOTE}
{_CONFIDENCE_NOTE}
"""


def build_header_prompt() -> str:
    """Focused prompt for the header band crop."""
    return f"""{_INTRO}

This image is the header band at the top of the sheet.

Return ONLY a single JSON object of the form:
{{
  "header": {{
    "ref_produit": {{"value": <digits or null>, "confidence": <0..1>}},
    "n_of": {{"value": <digits or null>, "confidence": <0..1>}},
    "qte": {{"value": <integer or null>, "confidence": <0..1>}},
    "annotation_serie": {{"value": <string or null>, "confidence": <0..1>}}
  }}
}}

Notes:
- "ref_produit" is the handwritten number after "Réf. Produit", "n_of" after \
"N° OF", "qte" after "Qté".
{_DIGIT_NOTE}
- "annotation_serie" is a SEPARATE extra handwritten annotation (e.g. a serial \
range like "500 -> 512"); never merge it into "ref_produit". Null if absent.
{_CONFIDENCE_NOTE}
"""


def build_prompt() -> str:
    """Full single-image prompt (whole sheet at once).

    Retained as a fallback / for backends that prefer one call; the Groq POC
    path uses the focused per-section prompts above, which read the cramped
    handwriting far more reliably (see GroqClient).
    """
    return f"""{_INTRO} The sheet has a printed header, a table of fixed \
operations with handwritten entries per row, and a control section.

Return ONLY a single JSON object (no markdown, no commentary) with this \
exact shape:

{{
  "header": {{
    "ref_produit": {{"value": <string or null>, "confidence": <0..1>}},
    "n_of": {{"value": <string or null>, "confidence": <0..1>}},
    "qte": {{"value": <integer or null>, "confidence": <0..1>}},
    "annotation_serie": {{"value": <string or null>, "confidence": <0..1>}}
  }},
  "operations": {{ <one key per operation row index> }},
  "controls": {{ <one key per control row index> }},
  "items": [ <one entry per physical part serial number visible on the sheet> ]
}}

"operations" and "controls" are OBJECTS keyed by stringified row index.

{_OPERATION_SHAPE}
Each "controls" entry additionally has "methode" and "resultat" as above.
Each "items" entry: {{"numero_serie": {{"value": <string or null>, "confidence": <0..1>}}}}

{_TABLE_NOTES}

The "operations" index order (index: operation name), Partie 1 then Partie 2:
{_numbered(_OPERATIONS)}

The "controls" index order (index: control label):
{_numbered(CONTROLE_ROWS)}
"""
