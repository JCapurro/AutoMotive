import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
ALLOWED_USER_IDS = {
    int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip().isdigit()
}

# How often the scheduler wakes up to look for due alerts.
TICK_INTERVAL_SECONDS = int(os.getenv("TICK_INTERVAL_SECONDS", "300"))
# Each alert is re-scraped at most once per this interval (default 6h).
ALERT_RESCRAPE_INTERVAL_SECONDS = int(os.getenv("ALERT_RESCRAPE_INTERVAL_SECONDS", str(6 * 3600)))
# Recommended listings whose `published_at` is older than this are dropped.
# When the source doesn't expose a date, only seen_listings + bootstrap apply.
RECOMMENDED_MAX_AGE_DAYS = int(os.getenv("RECOMMENDED_MAX_AGE_DAYS", "15"))
OPPORTUNITY_MIN_COMPARABLES = int(os.getenv("OPPORTUNITY_MIN_COMPARABLES", "5"))
DEFAULT_DISCOUNT_PCT = float(os.getenv("DEFAULT_DISCOUNT_PCT", "15"))

# Geocoding is used to turn listing location text into coordinates and then
# enforce a user-origin radius in kilometers.
GEOCODING_ENABLED = os.getenv("GEOCODING_ENABLED", "1").strip().lower() not in {
    "0", "false", "no", "off"
}
GEOCODING_USER_AGENT = os.getenv(
    "GEOCODING_USER_AGENT",
    "AutoMotiveAlerts/1.0 (local bot)",
).strip()

DB_PATH = str(ROOT / os.getenv("DB_PATH", "automotive.db"))
FB_STORAGE_STATE = str(ROOT / os.getenv("FB_STORAGE_STATE", "fb_state.json"))
ML_STORAGE_STATE = str(ROOT / os.getenv("ML_STORAGE_STATE", "ml_state.json"))

SOURCES = ["mercadolibre", "facebook", "v6", "kavak"]
