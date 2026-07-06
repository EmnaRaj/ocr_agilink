# Drop-folder auto-ingest

Drop scan files here (PDF / JPG / PNG) and — when `LOCAL_INBOX_ENABLED=1` — the
platform automatically uploads and runs them through the full pipeline, exactly
like a manual upload. Processed files are moved to `processed/`.

Enable it in `.env`:

    LOCAL_INBOX_ENABLED=1
    LOCAL_INBOX_DIR=/srv/inbox        # container path (host ./inbox is mounted here)
    LOCAL_INBOX_POLL_SECONDS=30

Then: `docker compose up -d --build worker beat`
