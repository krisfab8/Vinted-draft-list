"""Keep first-run evidence and operator feedback beside the authoritative listing."""
import json
from datetime import datetime, timezone

ISSUES = {'brand', 'fabric', 'size', 'material', 'price', 'copy', 'other'}


def capture(path, listing, **metrics):
    target = path / 'analysis.json'
    # Exclusive creation: later edits never replace the original result.
    try:
        with target.open('x') as out:
            json.dump({'captured_at': datetime.now(timezone.utc).isoformat(),
                       'listing': listing, **metrics}, out, indent=2)
    except FileExistsError:
        pass


def read(path):
    target = path / 'feedback.json'
    return json.loads(target.read_text()) if target.exists() else {'issues': [], 'notes': ''}


def save(path, body):
    if not isinstance(body, dict):
        raise ValueError('Choose an issue and enter any corrections.')
    issues, notes = body.get('issues', []), body.get('notes', '')
    if (not isinstance(issues, list) or len(issues) > len(ISSUES)
            or any(not isinstance(i, str) or i not in ISSUES for i in issues)
            or not isinstance(notes, str) or len(notes) > 2000):
        raise ValueError('Invalid feedback; notes must be under 2,000 characters.')
    capture(path, json.loads((path / 'listing.json').read_text()))
    result = {'issues': list(dict.fromkeys(issues)), 'notes': notes.strip(),
              'updated_at': datetime.now(timezone.utc).isoformat()}
    temporary = path / 'feedback.json.tmp'
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(path / 'feedback.json')
    return result
