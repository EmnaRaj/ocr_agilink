"""Microsoft Graph client for the SharePoint auto-ingest poller.

App-only (client-credentials) auth against an Azure AD app registration that has
Files.Read.All / Sites.Read.All application permissions (admin-consented). We
watch a folder with Graph's `delta` feed: the first call returns everything and a
`deltaLink`; each later call uses that link and returns ONLY what changed. The
link is persisted (IntegrationState) so polling is incremental and near
exactly-once. `msal`/`requests` are imported lazily so the API image doesn't need
them unless the poller actually runs (worker only).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings
from ..models import IntegrationState

GRAPH = "https://graph.microsoft.com/v1.0"
_CURSOR_KEY = "sharepoint_delta"


def _token() -> str:
    import msal

    app = msal.ConfidentialClientApplication(
        client_id=settings.sharepoint_client_id,
        authority=f"https://login.microsoftonline.com/{settings.sharepoint_tenant_id}",
        client_credential=settings.sharepoint_client_secret,
    )
    res = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in res:
        raise RuntimeError(
            f"SharePoint auth failed: {res.get('error')}: {res.get('error_description')}"
        )
    return res["access_token"]


def _drive_id(token: str, requests) -> str:
    if settings.sharepoint_drive_id:
        return settings.sharepoint_drive_id
    if not settings.sharepoint_site_id:
        raise RuntimeError("Set SHAREPOINT_DRIVE_ID or SHAREPOINT_SITE_ID.")
    r = requests.get(
        f"{GRAPH}/sites/{settings.sharepoint_site_id}/drive",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def _folder_item_id(token: str, drive: str, requests) -> str:
    folder = settings.sharepoint_folder_path.strip("/")
    if not folder:
        return "root"
    r = requests.get(
        f"{GRAPH}/drives/{drive}/root:/{folder}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def get_delta_cursor(db: Session) -> str | None:
    row = db.get(IntegrationState, _CURSOR_KEY)
    return row.value if row else None


def save_delta_cursor(db: Session, cursor: str | None) -> None:
    if not cursor:
        return
    row = db.get(IntegrationState, _CURSOR_KEY)
    if row:
        row.value = cursor
    else:
        db.add(IntegrationState(key=_CURSOR_KEY, value=cursor))
    db.commit()


def list_changed_files(cursor: str | None) -> tuple[list[dict], str | None]:
    """Return (new/changed files, next deltaLink). A file dict has id, name,
    etag, download_url, drive_id. A None/expired cursor restarts a full delta."""
    import requests

    token = _token()
    headers = {"Authorization": f"Bearer {token}"}
    if cursor:
        url = cursor
    else:
        drive = _drive_id(token, requests)
        folder_id = _folder_item_id(token, drive, requests)
        url = f"{GRAPH}/drives/{drive}/items/{folder_id}/delta"

    items: list[dict] = []
    while True:
        r = requests.get(url, headers=headers, timeout=60)
        if r.status_code == 410:  # cursor too old — Graph asks us to resync
            return list_changed_files(None)
        r.raise_for_status()
        data = r.json()
        for it in data.get("value", []):
            if it.get("file") and not it.get("deleted"):
                items.append(
                    {
                        "id": it["id"],
                        "name": it.get("name", ""),
                        "etag": it.get("eTag", ""),
                        "download_url": it.get("@microsoft.graph.downloadUrl"),
                        "drive_id": (it.get("parentReference") or {}).get("driveId"),
                    }
                )
        if data.get("@odata.nextLink"):
            url = data["@odata.nextLink"]
            continue
        return items, data.get("@odata.deltaLink")


def download(item: dict) -> bytes:
    import requests

    if item.get("download_url"):
        r = requests.get(item["download_url"], timeout=120)
        r.raise_for_status()
        return r.content
    token = _token()
    r = requests.get(
        f"{GRAPH}/drives/{item['drive_id']}/items/{item['id']}/content",
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    r.raise_for_status()
    return r.content
