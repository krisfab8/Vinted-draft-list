"""Fresh, independent analysis copies using the exact saved photo bytes."""
import json
import re
import shutil
import uuid
from app.services import listing_state
from app.services.measurements import PHOTO_ROLES


def prepare(root, source_folder, request_id):
    source = listing_state.item_path(root, source_folder)
    if not (source/'listing.json').is_file():
        raise FileNotFoundError('Original listing not found.')
    try:
        token = uuid.UUID(request_id).hex
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid analysis request.') from None
    target_folder = 'upload_retest_'+token
    target = listing_state.item_path(root, target_folder)
    baseline = json.loads((source/'listing.json').read_text())
    paths = []
    for path in source.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {'.jpg','.jpeg','.png','.webp'}:
            continue
        if path.stem in PHOTO_ROLES or re.fullmatch(r'extra_\d+', path.stem):
            paths.append(path)
    if not paths:
        raise ValueError('No saved garment photos are available. Restore the photo backup first.')
    return source, target, target_folder, baseline, paths


def copy_photos(source, target, source_folder, paths):
    target.mkdir(exist_ok=False)
    for path in paths:
        shutil.copyfile(path, target/path.name)
    roles = source/'photo_roles.json'
    if roles.is_file() and not roles.is_symlink():
        shutil.copyfile(roles, target/roles.name)
    (target/'reanalysis.json').write_text(json.dumps({'source':source_folder}))


def baseline_fields(listing):
    from app.services.description_layout import size_text
    from app.services.garment_text import detail
    return {'Brand': listing.get('brand') or '—', 'Size':size_text(listing) or '—',
            'Material':', '.join(listing.get('materials') or []) or '—',
            'Logo / print':detail(listing) or '—'}
