import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "claude-haiku")

GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID", "")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")

VINTED_EMAIL = os.getenv("VINTED_EMAIL", "")
VINTED_PASSWORD = os.getenv("VINTED_PASSWORD", "")

GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY", "")

SCHEMA_PATH = ROOT / "schemas" / "listing.schema.json"
PROMPTS_DIR = ROOT / "prompts"
ITEMS_DIR = ROOT / "items"

# Models
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

# Confidence threshold — below this, escalate to Sonnet
CONFIDENCE_THRESHOLD = 0.7

# Core photos to analyse (in priority order)
CORE_PHOTOS = ["front", "tag", "material", "back"]
