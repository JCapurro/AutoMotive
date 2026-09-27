import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Runtime files (.env, Playwright sessions) live at the repo root, as before
# the move to worker/.
ROOT = Path(__file__).resolve().parent.parent

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
# Fallbacks only: app_config (recommended_max_age_days, comparables) wins when set.
OPPORTUNITY_MIN_COMPARABLES = int(os.getenv("OPPORTUNITY_MIN_COMPARABLES", "5"))
# Deprecated by app_config.level_thresholds once the 0–100 score lands (F2).
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

# Supabase Postgres. Direct connection or the session pooler; with the
# transaction pooler (port 6543) prepared statements are disabled.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "5"))

FB_STORAGE_STATE = str(ROOT / os.getenv("FB_STORAGE_STATE", "fb_state.json"))
ML_STORAGE_STATE = str(ROOT / os.getenv("ML_STORAGE_STATE", "ml_state.json"))

SOURCES = ["mercadolibre", "facebook", "v6", "kavak"]
