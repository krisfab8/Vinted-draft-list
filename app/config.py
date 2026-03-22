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
# Set low (0.5) to avoid expensive Sonnet calls; user can correct via review card
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))

# Core photos to analyse (in priority order)
# Slots 1-4 are the primary analysis photos; back (slot 5) is optional but analyzed if present
CORE_PHOTOS = ["front", "brand", "model_size", "material"]

# eBay comp guidance (optional — app works without these)
EBAY_APP_ID = os.getenv("EBAY_APP_ID", "")
EBAY_CERT_ID = os.getenv("EBAY_CERT_ID", "")
# Discount applied to active eBay prices to proxy likely sold price on Vinted
EBAY_ACTIVE_TO_SOLD_DISCOUNT = float(os.getenv("EBAY_ACTIVE_TO_SOLD_DISCOUNT", "0.70"))

# Feature flags — set env vars to "0" to disable
# ENABLE_LABEL_AUTOCROP: crop OCR-critical label photos to remove background before sending
ENABLE_LABEL_AUTOCROP = os.getenv("ENABLE_LABEL_AUTOCROP", "1") == "1"
# ENABLE_CATEGORY_ITEM_TYPE_SLICE: further reduce category_rules prompt by item type
ENABLE_CATEGORY_ITEM_TYPE_SLICE = os.getenv("ENABLE_CATEGORY_ITEM_TYPE_SLICE", "1") == "1"
# ENABLE_PARALLEL_REREADS: run brand and material rereads concurrently (ThreadPoolExecutor)
ENABLE_PARALLEL_REREADS = os.getenv("ENABLE_PARALLEL_REREADS", "1") == "1"
# ENABLE_PRICE_MEMORY: inject price memory hints into listing writer prompt
ENABLE_PRICE_MEMORY = os.getenv("ENABLE_PRICE_MEMORY", "1") == "1"
# ENABLE_EBAY_COMPS: allow on-demand eBay comp fetching from the review page
ENABLE_EBAY_COMPS = os.getenv("ENABLE_EBAY_COMPS", "1") == "1"
