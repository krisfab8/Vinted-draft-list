"""Validate a listing dict (or JSON file) against listing.schema.json."""
import json
import sys
from pathlib import Path

import jsonschema

from app.config import SCHEMA_PATH

_schema = json.loads(SCHEMA_PATH.read_text())


def validate(listing: dict) -> list[str]:
    """Return list of validation error messages. Empty list means valid."""
    validator = jsonschema.Draft202012Validator(_schema)
    return [e.message for e in validator.iter_errors(listing)]


def validate_or_raise(listing: dict) -> None:
    errors = validate(listing)
    if errors:
        raise ValueError("Listing validation failed:\n" + "\n".join(f"  - {e}" for e in errors))


# Allow running as a script: python -m app.validate_listing path/to/listing.json
if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not path or not path.exists():
        print("Usage: python -m app.validate_listing <listing.json>")
        sys.exit(1)
    data = json.loads(path.read_text())
    errors = validate(data)
    if errors:
        print("INVALID:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("OK")
