# SharePoint auto-ingest — setup

When enabled, the platform watches a SharePoint folder and automatically runs the
full pipeline (download → extract → validate) on every **new** PDF dropped there.
Manual upload keeps working exactly as before — this only adds a second way in.

How it works: a `beat` scheduler fires a poller every `SHAREPOINT_POLL_SECONDS`.
The poller asks Microsoft Graph's `delta` API for *only what changed* in the
folder, pulls each new PDF, stores it, and enqueues the same `process_scan_batch`
job a manual upload uses. It's idempotent (a file is never ingested twice — by
SharePoint id+eTag and by content hash), and outbound-only (no inbound firewall
holes; works on-prem).

## What the client (Azure admin) must provide

Create one **Azure AD app registration** and hand us five values.

1. **Entra admin center** → *Microsoft Entra ID* → *App registrations* → **New
   registration**. Name it e.g. `Agilink Fiches Ingest`. Single tenant. No
   redirect URI needed. **Register**.
2. On the app's **Overview**, copy:
   - **Application (client) ID** → `SHAREPOINT_CLIENT_ID`
   - **Directory (tenant) ID** → `SHAREPOINT_TENANT_ID`
3. **Certificates & secrets** → **New client secret** → copy the secret **Value**
   (not the Id) → `SHAREPOINT_CLIENT_SECRET`. (Note its expiry — it must be
   rotated before it lapses.)
4. **API permissions** → **Add a permission** → *Microsoft Graph* →
   **Application permissions** → add **Sites.Read.All** and **Files.Read.All**
   → **Add permissions** → then **Grant admin consent** (the status must turn
   green). Application (not delegated) permissions are required — this runs with
   no signed-in user.
5. Identify the library to watch. Easiest: give us the **site URL** and the
   **folder** name; we resolve the rest. If you prefer to provide ids directly:
   - `SHAREPOINT_SITE_ID` — from
     `GET https://graph.microsoft.com/v1.0/sites/{hostname}:/sites/{site-name}`
     (looks like `contoso.sharepoint.com,<guid>,<guid>`), **or**
   - `SHAREPOINT_DRIVE_ID` — the specific document library's drive id.
   - `SHAREPOINT_FOLDER_PATH` — folder relative to the drive root, e.g. `Scans`
     or `Scans/Fiches` (leave blank to watch the whole library).

## Turn it on (our side)

In `.env`:

```
SHAREPOINT_ENABLED=1
SHAREPOINT_TENANT_ID=...
SHAREPOINT_CLIENT_ID=...
SHAREPOINT_CLIENT_SECRET=...
SHAREPOINT_SITE_ID=...            # or SHAREPOINT_DRIVE_ID
SHAREPOINT_FOLDER_PATH=Scans
SHAREPOINT_POLL_SECONDS=180
```

Then:

```
docker compose up -d --build worker beat
```

The `beat` service starts polling. Drop a PDF into the folder; within one poll
interval it appears in the app just like a manual upload, and runs through
extraction + validation automatically.

## Notes / operations

- **Security**: the client secret lives only in `.env` (never committed). The app
  has **read-only** Graph access. Scans are pulled over TLS and stored in the same
  MinIO bucket as manual uploads.
- **Latency** = up to one `SHAREPOINT_POLL_SECONDS` window (default 3 min).
- **First run** ingests every existing PDF in the folder once, then only new ones.
- **Deduplication**: re-polling, renames, or a file also uploaded manually will
  not create duplicates.
- **Secret rotation**: when the client secret expires, generate a new one and
  update `.env` + restart `beat`/`worker`.
