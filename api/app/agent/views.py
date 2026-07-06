"""Canonical DDL for the analytical views (specs/003).

Single source of truth for the read-only views the copilot queries. Both the
Alembic migration (`db/alembic/versions/a1f3c2d4e5b6_analytics_views.py`) and the
test fixture (`api/tests/conftest.py`) import these, so prod and test never drift.

The views flatten each fiche's ``raw_extraction`` JSONB into clean columns. Because
they derive from ``raw_extraction`` (not the relational ``operations``/``controls``/
``items`` tables, which are written once at ingest and never updated), they always
reflect user corrections and validations. Each ExtractedField leaf is
``{value, confidence, raw_text, source}`` read as ``->'field'->>'value'``. Array
fields are unnested with a typeof-guarded LATERAL so a null/failed extraction degrades
to zero rows instead of erroring.
"""

V_FICHES = """
CREATE OR REPLACE VIEW v_fiches AS
SELECT
    f.fiche_id,
    COALESCE(f.raw_extraction->'header'->'ref_produit'->>'value', p.ref_produit) AS ref_produit,
    p.designation AS designation,
    COALESCE(f.raw_extraction->'header'->'n_of'->>'value', w.n_of) AS n_of,
    COALESCE((f.raw_extraction->'header'->'qte'->>'value')::int, w.quantite) AS quantite,
    f.statut::text AS statut,
    f.date_creation,
    (f.raw_extraction->'meta'->>'overall_confidence')::float AS overall_confidence,
    COALESCE((f.raw_extraction->'meta'->>'validated')::boolean, false) AS validated,
    f.page_index
FROM fiches f
JOIN work_orders w ON w.of_id = f.of_id
JOIN products p ON p.product_id = w.product_id;
"""

V_OPERATIONS = """
CREATE OR REPLACE VIEW v_operations AS
SELECT
    f.fiche_id,
    op->>'partie' AS partie,
    op->>'nom_operation' AS nom_operation,
    (op->>'ordre')::int AS ordre,
    (op->'applicable'->>'value')::boolean AS applicable,
    op->'date_op'->>'value' AS date_op,
    op->'date_fin'->>'value' AS date_fin,
    op->'heure_debut'->>'value' AS heure_debut,
    op->'heure_fin'->>'value' AS heure_fin,
    (op->'qte_realisee'->>'value')::numeric AS qte_realisee,
    op->'outillage'->>'value' AS outillage,
    op->'matricule_operateur'->>'value' AS matricule_operateur,
    o.nom AS operateur_nom,
    (op->'applicable'->>'confidence')::float AS confidence
FROM fiches f
CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(f.raw_extraction->'operations') = 'array'
         THEN f.raw_extraction->'operations' ELSE '[]'::jsonb END
) AS op
LEFT JOIN operators o ON o.matricule = (op->'matricule_operateur'->>'value');
"""

V_CONTROLS = """
CREATE OR REPLACE VIEW v_controls AS
SELECT
    f.fiche_id,
    c->>'type_controle' AS type_controle,
    c->'methode'->>'value' AS methode,
    (c->'resultat'->>'value')::boolean AS resultat,
    c->'matricule_operateur'->>'value' AS matricule_operateur,
    o.nom AS operateur_nom,
    (c->'resultat'->>'confidence')::float AS confidence
FROM fiches f
CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(f.raw_extraction->'controls') = 'array'
         THEN f.raw_extraction->'controls' ELSE '[]'::jsonb END
) AS c
LEFT JOIN operators o ON o.matricule = (c->'matricule_operateur'->>'value');
"""

V_ITEMS = """
CREATE OR REPLACE VIEW v_items AS
SELECT
    f.fiche_id,
    it->'numero_serie'->>'value' AS numero_serie
FROM fiches f
CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(f.raw_extraction->'items') = 'array'
         THEN f.raw_extraction->'items' ELSE '[]'::jsonb END
) AS it;
"""

V_VALIDATION = """
CREATE OR REPLACE VIEW v_validation AS
SELECT
    f.fiche_id,
    v->>'scope' AS scope,
    v->>'location' AS location,
    v->>'field' AS field,
    v->>'level' AS level,
    v->>'code' AS code,
    v->>'message' AS message
FROM fiches f
CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(f.raw_extraction->'validation') = 'array'
         THEN f.raw_extraction->'validation' ELSE '[]'::jsonb END
) AS v;
"""

# Order matters for creation (none depend on each other, but kept stable) and for
# teardown (reverse).
ANALYTICS_VIEWS: list[str] = [V_FICHES, V_OPERATIONS, V_CONTROLS, V_ITEMS, V_VALIDATION]
VIEW_NAMES: list[str] = ["v_fiches", "v_operations", "v_controls", "v_items", "v_validation"]

# The only tables/views run_sql may read (used to build the read-only grant + the
# schema description the model sees).
REFERENTIAL_TABLES: list[str] = ["products", "work_orders", "operators", "tools"]
QUERYABLE: list[str] = VIEW_NAMES + REFERENTIAL_TABLES
