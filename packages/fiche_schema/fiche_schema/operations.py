"""The fixed operation lists from the Fiche Suiveuse template.

The form geometry never changes, so the operation names and their order are
constants, not data. This module is the single source of truth — the DB seed,
the extraction schema, and the VLM prompt all derive from it.
"""

from __future__ import annotations

PARTIE_1_OPERATIONS: tuple[str, ...] = (
    "Dégainage",
    "Soudure et/ou Auto-Soudeur",
    "Dénudage Fil",
    "Sertissage",
    "Enfichage",
    "Rétention",
    "Serrage des raccords arrières",
    "Serrage capots",
    "Serrage des colliers Band'it, Tinel-Lock,..",
    "Raccordement reprise de blindage (nœud de frette)",
    "Passage des gaines, tresses, marquages, accessoires, / Retreint",
    "Ajustement",
)

PARTIE_2_OPERATIONS: tuple[str, ...] = (
    "Dégainage",
    "Soudure et/ou Auto-Soudeur",
    "Dénudage Fil",
    "Sertissage",
    "Enfichage",
    "Rétention",
    "Serrage des raccords arrières",
    "Serrage capots",
    "Serrage des colliers Band'it, Tinel-Lock,..",
    "Raccordement reprise de blindage (nœud de frette)",
    "Test électrique avant surmoulage",
    "Potting / surmoulage",
    "Finition (pièce moulée -marquage -gaine ..)",
)

# Contrôle rows are not generic operations — each has its own semantics
# (methode for the electrical check, resultat for final/correspondance) —
# but they still occupy fixed rows 1..3 in template order.
CONTROLE_ROWS: tuple[str, ...] = (
    "Contrôle électrique",
    "Contrôle final",
    "Le numéro de série sur le rapport de test électrique correspond au "
    "numéro de série du produit.",
)

assert len(PARTIE_1_OPERATIONS) == 12
assert len(PARTIE_2_OPERATIONS) == 13
assert len(CONTROLE_ROWS) == 3
