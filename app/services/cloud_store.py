"""Durable copy of hosted drafts in S3-compatible storage (Backblaze B2).

Render's free plan wipes local files on every restart. When the four B2_*
variables are set, each item folder is stored as one backup zip (the same
format as the phone backup) and restored into an empty server on startup.

Safety rules:
- restore never overwrites an existing local item (item_backup.restore refuses)
- a remote copy is only deleted after this process saw the item locally and
  then saw it disappear, so an empty or failed startup can never wipe the bucket
- failures are logged and retried; they never break a request
"""
import json
import logging
import os
import threading
from pathlib import Path

from app.services import item_backup

log = logging.getLogger("cloud_store")

PREFIX = "items/"
REQUIRED = ("B2_KEY_ID", "B2_APP_KEY", "B2_BUCKET", "B2_ENDPOINT")
SYNC_INTERVAL_SECONDS = 60
DEBOUNCE_SECONDS = 2


def missing_settings():
    return [name for name in REQUIRED if not os.getenv(name, "").strip()]


def make_client():
    import boto3
    from botocore.config import Config

    endpoint = os.environ["B2_ENDPOINT"].strip().rstrip("/")
    if not endpoint.startswith("http"):
        endpoint = "https://" + endpoint
    # s3.<region>.backblazeb2.com -> <region>
    host = endpoint.split("://", 1)[1]
    region = host.split(".")[1] if host.startswith("s3.") and host.count(".") >= 2 else "us-east-1"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=os.environ["B2_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["B2_APP_KEY"].strip(),
        config=Config(connect_timeout=5, read_timeout=60, retries={"max_attempts": 3}),
    )


def _key(folder):
    return f"{PREFIX}{folder}.zip"


def _signature(folder_path):
    """Changes whenever a file in the item folder or its sale record changes."""
    files = sorted(
        (f.name, f.stat().st_size, f.stat().st_mtime_ns)
        for f in folder_path.iterdir() if f.is_file() and not f.is_symlink()
    )
    try:
        from app.services import sales_history
        sale = sales_history.get(folder_path.name)
    except Exception:
        sale = None
    return json.dumps([files, sale], sort_keys=True, default=str)


class CloudStore:
    def __init__(self, client, bucket, items_dir, on_restored=None):
        self.client = client
        self.bucket = bucket
        self.items_dir = Path(items_dir)
        self.on_restored = on_restored
        self._known = {}  # folder -> signature last uploaded or restored
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self.status = {"enabled": True, "restored": 0, "uploaded": 0, "deleted": 0,
                       "last_error": None}

    def _local_folders(self):
        if not self.items_dir.is_dir():
            return {}
        return {p.name: p for p in self.items_dir.iterdir()
                if p.is_dir() and item_backup.FOLDER.fullmatch(p.name)
                and (p / "listing.json").is_file()}

    def _remote_folders(self):
        folders, token = [], None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": PREFIX}
            if token:
                kwargs["ContinuationToken"] = token
            page = self.client.list_objects_v2(**kwargs)
            for obj in page.get("Contents", []):
                name = obj["Key"][len(PREFIX):]
                if name.endswith(".zip") and item_backup.FOLDER.fullmatch(name[:-4]):
                    folders.append(name[:-4])
            if not page.get("IsTruncated"):
                return folders
            token = page["NextContinuationToken"]

    def restore_all(self):
        """Bring back every stored item that is missing locally."""
        restored = []
        with self._lock:
            try:
                remote = self._remote_folders()
            except Exception as error:
                self._fail("list bucket", error)
                return restored
            local = self._local_folders()
            for folder in remote:
                if folder in local:
                    continue
                try:
                    body = self.client.get_object(Bucket=self.bucket, Key=_key(folder))["Body"].read()
                    item_backup.restore(body, self.items_dir)
                    self._known[folder] = _signature(self.items_dir / folder)
                    restored.append(folder)
                    if self.on_restored:
                        self.on_restored(folder)
                except Exception as error:
                    self._fail(f"restore {folder}", error)
            self.status["restored"] += len(restored)
        log.warning("Cloud storage: %d stored drafts, %d restored", len(remote), len(restored))
        return restored

    def sync(self):
        """Upload changed items; delete remote copies of items deleted here."""
        with self._lock:
            local = self._local_folders()
            for folder, path in local.items():
                try:
                    signature = _signature(path)
                    if self._known.get(folder) == signature:
                        continue
                    json.loads((path / "listing.json").read_text())  # skip half-written saves
                    data = item_backup.export(self.items_dir, folder)
                    self.client.put_object(Bucket=self.bucket, Key=_key(folder), Body=data,
                                           ContentType="application/zip")
                    self._known[folder] = signature
                    self.status["uploaded"] += 1
                except Exception as error:
                    self._fail(f"upload {folder}", error)
            for folder in [f for f in self._known if f not in local]:
                try:
                    self.client.delete_object(Bucket=self.bucket, Key=_key(folder))
                    del self._known[folder]
                    self.status["deleted"] += 1
                except Exception as error:
                    self._fail(f"delete {folder}", error)

    def request_sync(self):
        self._wake.set()

    def start(self):
        def loop():
            while True:
                self._wake.wait(SYNC_INTERVAL_SECONDS)
                if self._wake.is_set():
                    self._wake.clear()
                    threading.Event().wait(DEBOUNCE_SECONDS)
                    self._wake.clear()
                self.sync()
        threading.Thread(target=loop, name="cloud-store-sync", daemon=True).start()

    def _fail(self, action, error):
        # Exception text from botocore names the operation, never the secret key.
        message = f"{action} failed: {type(error).__name__}: {error}"
        self.status["last_error"] = message[:300]
        log.error("Cloud storage: %s", message)


def from_environment(items_dir, on_restored=None):
    """Return a started CloudStore, or None when B2 is not configured."""
    missing = missing_settings()
    if missing:
        if len(missing) < len(REQUIRED):
            log.error("Cloud storage disabled: missing %s", ", ".join(missing))
        else:
            log.warning("Cloud storage not configured; drafts are lost when the server restarts")
        return None
    store = CloudStore(make_client(), os.environ["B2_BUCKET"].strip(), items_dir, on_restored)
    store.restore_all()
    store.sync()
    store.start()
    return store
