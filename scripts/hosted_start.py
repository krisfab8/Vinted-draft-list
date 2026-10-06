"""Attach existing file-based state to one durable disk, then start Gunicorn."""
import os
import shutil
from pathlib import Path


def prepare_storage(root, storage):
    root, storage = Path(root), Path(storage)
    storage.mkdir(parents=True, exist_ok=True)
    for name in ("data", "items"):
        source, target = root / name, storage / name
        target.mkdir(exist_ok=True)
        if source.is_symlink():
            if source.resolve() != target.resolve():
                raise RuntimeError(f"Unexpected existing {name} storage link")
            continue
        if source.exists():
            for child in source.iterdir():
                destination = target / child.name
                if not destination.exists():
                    if child.is_dir():
                        shutil.copytree(child, destination)
                    else:
                        shutil.copy2(child, destination)
            shutil.rmtree(source)
        source.symlink_to(target, target_is_directory=True)
    source, target = root / "cost_log.csv", storage / "cost_log.csv"
    if not source.is_symlink():
        if source.exists() and not target.exists():
            shutil.copy2(source, target)
        source.unlink(missing_ok=True)
        source.symlink_to(target)


if __name__ == "__main__":
    os.environ.setdefault("ENABLE_SINGLE_PASS", "0")
    os.umask(0o077)
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    # Smoke-test packaged OCR before accepting uploads (no photos or paid calls).
    import sys
    sys.path.insert(0, str(root))
    from app.services.label_reader import _engine, smoke_test
    from PIL import Image
    _engine()(Image.new("RGB", (64, 64), "white"))
    print("Local composition OCR ready (rapidocr-onnxruntime 1.4.4)", flush=True)
    print("Composition recovery smoke: " + str(smoke_test()), flush=True)
    prepare_storage(root, os.getenv("APP_STORAGE_PATH", "/var/data/vinted"))
    os.execvp("gunicorn", [
        "gunicorn", "app.hosted:create_app()", "--bind", f"0.0.0.0:{os.getenv('PORT', '10000')}",
        "--workers", "1", "--threads", "1", "--timeout", "240",
        "--access-logfile", "-", "--error-logfile", "-",
    ])
