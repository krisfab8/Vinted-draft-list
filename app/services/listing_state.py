"""Atomic item writes and revision checks shared by every review surface."""
import hashlib
import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

_mutex = threading.Lock()
_locks = {}


def item_path(root, folder):
    root = Path(root).resolve()
    if not isinstance(folder, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', folder):
        raise ValueError('Invalid item folder.')
    path = (root / folder).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError('Invalid item folder.')
    return path


@contextmanager
def locked(root, folder):
    path = item_path(root, folder)
    with _mutex:
        lock = _locks.setdefault(str(path), threading.RLock())
    with lock:
        directory = Path(root) / '_locks'
        directory.mkdir(parents=True, exist_ok=True)
        # Keep locks outside item directories so deleting an item cannot replace
        # the inode another worker is using. Linux hosting and Windows local app.
        with (directory / (folder + '.lock')).open('a+b') as handle:
            if os.name == 'nt':
                import msvcrt
                handle.write(b'0'); handle.flush(); handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield path
            finally:
                if os.name == 'nt':
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def revision(path):
    from app.services import sales_history
    listing = path / 'listing.json'
    if not listing.exists():
        return None
    digest = hashlib.sha256(listing.read_bytes())
    digest.update(json.dumps(sales_history.get(path.name), sort_keys=True).encode())
    return digest.hexdigest()


def write(path, value):
    """A failed serialization/replacement leaves the previous file untouched."""
    path = Path(path)
    encoded = json.dumps(value, indent=2, allow_nan=False)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
