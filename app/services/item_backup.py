"""Restore an authenticated operator's item backup; never import configuration/auth."""
import io
import json
from datetime import datetime
import re
import tempfile
import zipfile
from pathlib import Path
from PIL import Image
from app.validate_listing import normalize_generated_listing, validate_or_raise
from app.services import model_usage

FOLDER = re.compile(r'upload_(?:[a-f0-9]{8}|retest_[a-f0-9]{32})')
PHOTO = re.compile(r'(?:front|brand|model_size|material|back|extra_\d{2}|measure_(?:pit_to_pit|length|sleeve))\.(?:jpg|jpeg|png|webp)')


STUB_MARKER = '_cloud.json'   # item restored as a summary; full files still in the cloud
THUMB = '_thumb.jpg'          # small preview kept with summaries (drafts cards)
EXTRA_FILES = ('analysis.json', 'feedback.json', 'reanalysis.json')


def is_stub(folder):
    return (Path(folder) / STUB_MARKER).is_file()


def backup_files(folder):
    """{name: size} of the files a backup carries (besides listing/photo_roles), including
    files that are still only in the cloud for a summary-restored item."""
    folder = Path(folder)
    files = {}
    try:
        files.update(json.loads((folder / STUB_MARKER).read_text()).get('files') or {})
    except (OSError, ValueError, AttributeError):
        pass
    for path in folder.iterdir() if folder.is_dir() else []:
        if path.is_file() and not path.is_symlink() and (PHOTO.fullmatch(path.name) or path.name in EXTRA_FILES):
            files[path.name] = path.stat().st_size
    return files


def revision(folder):
    """Stable fingerprint of an item's content: the same before and after a restore, so
    phones don't re-download unchanged items after the server wakes up."""
    import hashlib
    folder = Path(folder)
    digest = hashlib.sha1()
    for name in ('listing.json', 'photo_roles.json'):
        try:
            digest.update((folder / name).read_bytes())
        except OSError:
            pass
        digest.update(b'\0')
    digest.update(json.dumps(sorted(backup_files(folder).items())).encode())
    return digest.hexdigest()[:16]


def summary(folder):
    """Small cloud summary of an item: listing, photo roles, file sizes, a tiny preview."""
    import base64
    folder = Path(folder)
    thumb = None
    for role in ('front', 'back', 'brand'):
        source = next((folder / f'{role}{ext}' for ext in ('.jpg', '.jpeg', '.png', '.webp')
                       if (folder / f'{role}{ext}').is_file()), None)
        if source:
            with Image.open(source) as image:
                preview = image.convert('RGB')
                preview.thumbnail((360, 360))
                out = io.BytesIO()
                preview.save(out, 'JPEG', quality=70)
                thumb = base64.b64encode(out.getvalue()).decode()
            break
    roles = folder / 'photo_roles.json'
    return {'listing': (folder / 'listing.json').read_text(),
            'photo_roles': roles.read_text() if roles.is_file() else None,
            'files': {k: v for k, v in backup_files(folder).items()}, 'thumb': thumb}


def restore_summary(data, items_dir, folder):
    """Create a summary-only item (listing + preview); full files are fetched on first open."""
    import base64
    if not FOLDER.fullmatch(folder):
        raise ValueError('Invalid item folder.')
    listing = json.loads(data['listing'])
    if not isinstance(listing, dict):
        raise ValueError('Invalid listing.')
    target = Path(items_dir) / folder
    if target.exists():
        raise ValueError('Item already exists; restore does not overwrite seller edits.')
    Path(items_dir).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=items_dir) as temp:
        stage = Path(temp) / folder; stage.mkdir()
        (stage / 'listing.json').write_text(data['listing'])
        if data.get('photo_roles'):
            json.loads(data['photo_roles'])
            (stage / 'photo_roles.json').write_text(data['photo_roles'])
        if data.get('thumb'):
            (stage / THUMB).write_bytes(base64.b64decode(data['thumb']))
        files = {str(k): int(v) for k, v in (data.get('files') or {}).items()
                 if PHOTO.fullmatch(str(k)) or str(k) in EXTRA_FILES}
        (stage / STUB_MARKER).write_text(json.dumps({'files': files}))
        stage.rename(target)


def fill_stub(data, items_dir, folder):
    """Add the full files from a backup zip to a summary-only item; listing is left as is."""
    target = Path(items_dir) / folder
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            parts = info.filename.split('/')
            if len(parts) != 3 or parts[0] != 'items' or parts[1] != folder:
                continue
            name = parts[2]
            if not (PHOTO.fullmatch(name) or name in EXTRA_FILES) or (target / name).exists():
                continue
            if info.file_size > 30 * 1024 * 1024:
                raise ValueError('Backup file too large.')
            content = archive.read(info)
            if PHOTO.fullmatch(name):
                with Image.open(io.BytesIO(content)) as image:
                    if image.width * image.height > 50_000_000:
                        raise ValueError('Photo exceeds pixel limit.')
                    image.verify()
            tmp = target / (name + '.part')
            tmp.write_bytes(content)
            tmp.replace(target / name)
    (target / STUB_MARKER).unlink(missing_ok=True)


def folders_in(data):
    """Item folders named inside a backup zip (empty if it isn't one)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return {name.split('/')[1] for name in archive.namelist()
                    if name.startswith('items/') and name.count('/') == 2}
    except zipfile.BadZipFile:
        return set()


def restore(data, items_dir):
    if len(data) > 30*1024*1024:
        raise ValueError('Backup too large.')
    groups, events, sales_rows = {}, [], []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if len(infos) > 500 or sum(i.file_size for i in infos) > 100*1024*1024:
            raise ValueError('Backup limits exceeded.')
        seen=set()
        for info in infos:
            if info.filename in seen or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Duplicate or linked backup entries.')
            seen.add(info.filename)
            if info.filename == 'model_calls.json':
                events=json.loads(archive.read(info))
                continue
            if info.filename == 'sales_history.json':
                sales_rows = json.loads(archive.read(info))
                continue
            parts=info.filename.split('/')
            if len(parts)!=3 or parts[0]!='items' or not FOLDER.fullmatch(parts[1]):
                raise ValueError('Invalid backup path.')
            name=parts[2]
            if name not in ('listing.json','photo_roles.json','analysis.json','feedback.json','reanalysis.json') and not PHOTO.fullmatch(name):
                raise ValueError('Unsupported backup file.')
            content=archive.read(info)
            if PHOTO.fullmatch(name):
                with Image.open(io.BytesIO(content)) as image:
                    if image.width*image.height > 50_000_000:
                        raise ValueError('Photo exceeds pixel limit.')
                    image.verify()
            else:
                json.loads(content)
            groups.setdefault(parts[1],{})[name]=content
    for folder, files in groups.items():
        if 'listing.json' not in files:
            raise ValueError('Backup item has no listing.')
        listing=json.loads(files['listing.json'])
        # Older UI edits can store unknown optional values as null. Use the
        # same normalization as generated listings, retaining required errors.
        normalize_generated_listing(listing)
        validate_or_raise(listing)
        target=(Path(items_dir)/folder)
        if target.exists():
            raise ValueError('Item already exists; restore does not overwrite seller edits.')
        listing['folder']=folder
        listing['photos_folder']=str(target)
        # Old phone backups can reintroduce the pre-update generated layout.
        # Migrate structured details once; keep free text and exact item facts.
        from app.services import description_layout
        if not listing.get('description_layout_version'):
            description_layout.recover_tag(listing)
            description_layout.apply(listing)
        files['listing.json']=json.dumps(listing,indent=2).encode()
    if not isinstance(events,list) or any(not isinstance(e,dict) or not re.fullmatch(r'[a-f0-9]{32}',str(e.get('id',''))) for e in events):
        raise ValueError('Invalid usage ledger.')
    Path(items_dir).mkdir(parents=True,exist_ok=True)
    from app.services import sales_history
    sales_history.restore(sales_rows)
    for folder, files in groups.items():
        with tempfile.TemporaryDirectory(dir=items_dir) as temp:
            stage=Path(temp)/folder;stage.mkdir()
            for name, content in files.items():
                (stage/name).write_bytes(content)
            stage.rename(Path(items_dir)/folder)
    # Only known accounting fields; no arbitrary keys or credential files.
    allowed={'id','run_id','item','timestamp','stage','model','input_tokens','output_tokens',
             'cache_creation_input_tokens','cache_read_input_tokens','cost_gbp','cost_usd',
             'error_type','stop_reason','latency_ms','rate_version','usd_to_gbp','billing_status',
             'web_search_requests'}
    def well_formed(event):
        counts=('input_tokens','output_tokens','cache_creation_input_tokens','cache_read_input_tokens','web_search_requests')
        if any(event.get(k) is not None and (not isinstance(event[k],int) or isinstance(event[k],bool) or not 0<=event[k]<10**9)
               for k in counts):
            return False
        try:
            datetime.fromisoformat(str(event.get('timestamp','')).replace('Z','+00:00'))
        except ValueError:
            return False
        return all(event.get(k) is None or (isinstance(event[k],(int,float)) and not isinstance(event[k],bool) and 0<=event[k]<1000)
                   for k in ('cost_gbp','cost_usd'))
    events=[e for e in events if well_formed(e)]
    existing={e['id'] for e in model_usage.read_events()}
    if events:
        model_usage.LEDGER_PATH.parent.mkdir(parents=True,exist_ok=True)
        with model_usage.LEDGER_PATH.open('a') as out:
            for event in events:
                if event['id'] not in existing:
                    out.write(json.dumps({k:v for k,v in event.items() if k in allowed})+'\n')
                    existing.add(event['id'])
    return list(groups)


def export(items_dir, selected_folder=None):
    with export_file(items_dir, selected_folder) as spool:
        return spool.read()


def export_file(items_dir, selected_folder=None):
    """The backup zip in a temporary file (kept in memory only while small), rewound.
    Photos are stored as-is: JPEGs don't compress, so deflating them only costs CPU."""
    output=tempfile.SpooledTemporaryFile(max_size=1024*1024)
    try:
        _write_zip(output, items_dir, selected_folder)
    except BaseException:
        output.close()
        raise
    output.seek(0)
    return output


def _write_zip(output, items_dir, selected_folder):
    total=0
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        if selected_folder is not None and not FOLDER.fullmatch(selected_folder):
            raise ValueError("Invalid item folder.")
        folders = [Path(items_dir)/selected_folder] if selected_folder else Path(items_dir).iterdir()
        for folder in folders:
            if not folder.is_dir() or not FOLDER.fullmatch(folder.name) or not (folder/'listing.json').is_file():
                continue
            if is_stub(folder):
                # Photos are still only in the cloud: never hand out an incomplete backup.
                raise ValueError('Photos are still downloading; try again shortly.')
            for file in folder.iterdir():
                if file.is_symlink() or not file.is_file():
                    continue
                if file.name not in ('listing.json','photo_roles.json','analysis.json','feedback.json','reanalysis.json') and not PHOTO.fullmatch(file.name):
                    continue
                total+=file.stat().st_size
                if total>100*1024*1024:
                    raise ValueError('Backup too large; export fewer items.')
                archive.write(file,'items/'+folder.name+'/'+file.name,
                              compress_type=zipfile.ZIP_STORED if PHOTO.fullmatch(file.name) else zipfile.ZIP_DEFLATED)
        events = model_usage.read_events()
        if selected_folder:
            events = [event for event in events if event.get('item') == selected_folder]
        archive.writestr('model_calls.json',json.dumps(events))
        from app.services import sales_history
        rows = sales_history.read_all()
        if selected_folder: rows = [row for row in rows if row['folder'] == selected_folder]
        archive.writestr('sales_history.json', json.dumps(rows))
