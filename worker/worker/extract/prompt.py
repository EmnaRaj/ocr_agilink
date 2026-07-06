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
    '(write the digits joined together, with no spaces between them).\n'
    '- LOOK TWICE AT THESE CONFUSION PAIRS before settling on a digit: 0 vs 6, '
    '5 vs 9, 5 vs 8, 8 vs 6, 4 vs 9, 4 vs 7, 1 vs 7, 1 vs 2, 2 vs 8, 3 vs 8, '
    '4 vs 1 (an angular open-top "4" — as in a matricule ending 164 — is often '
    'misread as "1"; check the last digit of matricules especially). '
    'If a stroke could plausibly be '
    'either of a pair, look at how that SAME writer forms the unambiguous '
    'digits elsewhere on the page (e.g. another clear "9" or "0") and match '
    'the stroke shape to decide — do not just pick the more common-looking '
    'reading. If you remain genuinely unsure between two digits, report the '
    'value you find more likely but lower "confidence" accordingly (e.g. '
    '<=0.5) rather than reporting it at full confidence.'
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
  "date_op": {"value": null, "confidence": 0.0, "raw_text": <"DD/MM" you read, or omit>},
  "date_fin": {"value": null, "confidence": 0.0, "raw_text": <"DD/MM" you read, or omit>},
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
columns. The date is day/month only with NO year anywhere on \
the sheet; the 1-2 digit number just to its right is the SEPARATE \
quantity, not a year. Never concatenate them, never treat a 1-2 digit number \
as a year. Always set every "date_op"/"date_fin" value to null and put the \
day/month text in "raw_text", written with a SLASH and zero-padded as \
"DD/MM" — e.g. "23/03", "07/11" (never "23.3", never "23.03.96").
- DATES GENERALLY INCREASE down the sheet: operations are performed roughly in \
order, so a row's date is usually the same as, or later than, the rows above \
it. Use this ONLY as a sanity check when a date digit is ambiguous (a reading \
that breaks the order is more likely a misread — re-examine it) — but do NOT \
force ordering; genuine out-of-order dates can occur, so never change a date \
you read clearly just to make it ascending.
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
- "outillage" is NEVER a time: a value shaped like "HH:MM" (e.g. "14:15") is a \
time and belongs in "heure_debut"/"heure_fin", never in "outillage".
- TWO OPERATORS ON ONE ROW: if the matricule cell holds TWO operator numbers \
(written as "347/338", "347-338", or one stacked above the other), the \
operation was performed by two operators — capture BOTH, joined by a single \
"/", as the value (e.g. "347/338"). Do not drop one or pick only one.
- ONE OPERATOR USUALLY FILLS THE WHOLE SECTION: the matricule column is \
typically the SAME number on every filled row of a given Partie. Before \
reporting a row's matricule as different from the rows above/below it, \
re-examine that digit carefully — a lone outlier is much more likely a \
misread than a genuine mid-section operator change. If still unsure, keep \
your best reading but lower its confidence rather than reporting it at face \
value.
{_DIGIT_NOTE}
- CRITICAL — ROW IDENTITY: do NOT count rows or guess positions. For each \
filled row, READ the PRINTED operation name on the far left of that row and \
copy it into "operation". The handwriting on a line always belongs to the \
printed label printed on that same line — never to the line above or below. \
The three "Serrage …" rows (raccords arrières / capots / colliers Band'it) \
are different operations; read the full label to tell them apart.
{_CONFIDENCE_NOTE}"""


_OPERATION_FIELDS = """  "applicable": {"value": <true|false|null>, "confidence": <0..1>},
  "date_op": {"value": null, "confidence": 0.0, "raw_text": <"DD/MM" you read, or omit>},
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
- REF. PRODUIT IS 8 DIGITS, often written in TWO groups with a space, e.g. \
"1010 8006" = "10108006". Read EVERY digit group of the ref and CONCATENATE them \
into one 8-digit value — do NOT stop at the first group, and do NOT drop a group \
because of a gap. If you only see ~4 digits, look again to the right for the rest.
- The header is often cluttered with other handwriting around the ref \
(parentheses like "(602)(838-889)", arrows, crossed-out numbers, "ok"). These are \
NOT part of ref_produit — read only the digits on the "Réf. Produit" line itself.
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
