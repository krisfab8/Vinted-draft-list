"""Restore an authenticated operator's item backup; never import configuration/auth."""
import io
import json
import re
import tempfile
import zipfile
from pathlib import Path
from PIL import Image
from app.validate_listing import validate_or_raise
from app.services import model_usage

FOLDER = re.compile(r'upload_[a-f0-9]{8}')
PHOTO = re.compile(r'(?:front|brand|model_size|material|back|extra_\d{2}|measure_(?:pit_to_pit|length|sleeve))\.(?:jpg|jpeg|png|webp)')


def restore(data, items_dir):
    if len(data) > 30*1024*1024:
        raise ValueError('Backup too large.')
    groups, events = {}, []
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
            parts=info.filename.split('/')
            if len(parts)!=3 or parts[0]!='items' or not FOLDER.fullmatch(parts[1]):
                raise ValueError('Invalid backup path.')
            name=parts[2]
            if name not in ('listing.json','photo_roles.json','analysis.json','feedback.json') and not PHOTO.fullmatch(name):
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
        validate_or_raise(listing)
        target=(Path(items_dir)/folder)
        if target.exists():
            raise ValueError('Item already exists; restore does not overwrite seller edits.')
        listing['folder']=folder
        listing['photos_folder']=str(target)
        files['listing.json']=json.dumps(listing,indent=2).encode()
    if not isinstance(events,list) or any(not isinstance(e,dict) or not re.fullmatch(r'[a-f0-9]{32}',str(e.get('id',''))) for e in events):
        raise ValueError('Invalid usage ledger.')
    Path(items_dir).mkdir(parents=True,exist_ok=True)
    for folder, files in groups.items():
        with tempfile.TemporaryDirectory(dir=items_dir) as temp:
            stage=Path(temp)/folder;stage.mkdir()
            for name, content in files.items():
                (stage/name).write_bytes(content)
            stage.rename(Path(items_dir)/folder)
    # Only known accounting fields; no arbitrary keys or credential files.
    allowed={'id','run_id','item','timestamp','stage','model','input_tokens','output_tokens',
             'cache_creation_input_tokens','cache_read_input_tokens','cost_gbp','cost_usd',
             'error_type','stop_reason','latency_ms','rate_version','usd_to_gbp','billing_status'}
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
    output=io.BytesIO()
    total=0
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        if selected_folder is not None and not FOLDER.fullmatch(selected_folder):
            raise ValueError("Invalid item folder.")
        folders = [Path(items_dir)/selected_folder] if selected_folder else Path(items_dir).iterdir()
        for folder in folders:
            if not folder.is_dir() or not FOLDER.fullmatch(folder.name) or not (folder/'listing.json').is_file():
                continue
            for file in folder.iterdir():
                if file.is_symlink() or not file.is_file():
                    continue
                if file.name not in ('listing.json','photo_roles.json','analysis.json','feedback.json') and not PHOTO.fullmatch(file.name):
                    continue
                total+=file.stat().st_size
                if total>100*1024*1024:
                    raise ValueError('Backup too large; export fewer items.')
                archive.write(file,'items/'+folder.name+'/'+file.name)
        events = model_usage.read_events()
        if selected_folder:
            events = [event for event in events if event.get('item') == selected_folder]
        archive.writestr('model_calls.json',json.dumps(events))
    return output.getvalue()
