-- Optional defense-in-depth for the analytical copilot's run_sql tool (specs/003).
--
-- The app already enforces read-only at three layers in code (SELECT-only parser,
-- read-only transaction, statement timeout — see api/app/agent/sql.py). This adds a
-- fourth: a dedicated Postgres login role that can ONLY SELECT the analytical views
-- and the immutable referential tables. Point READONLY_DATABASE_URL at this role and
-- run_sql will connect as it instead of the app user.
--
-- Run once, as a superuser/owner, against the app database. Choose a real password.
--   psql "$DATABASE_URL" -v pw="'choose-a-strong-password'" -f db/readonly_role.sql

CREATE ROLE agilink_readonly LOGIN PASSWORD :pw;

GRANT CONNECT ON DATABASE "fiches" TO agilink_readonly;  -- adjust db name if different
GRANT USAGE ON SCHEMA public TO agilink_readonly;

-- The only objects the tool may read.
GRANT SELECT ON v_fiches, v_operations, v_controls, v_items, v_validation TO agilink_readonly;
GRANT SELECT ON products, work_orders, operators, tools TO agilink_readonly;

-- Explicitly ensure no access to the stale relational value tables or write paths.
-- (No GRANT means no access by default; listed here as intent.)
-- REVOKE ALL ON operations, controls, items, fiches, scans, audit_log FROM agilink_readonly;

-- Then set, e.g.:
--   READONLY_DATABASE_URL=postgresql+psycopg://agilink_readonly:<pw>@postgres:5432/fiches
