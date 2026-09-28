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

# How often the crawl loop wakes up to look for due crawl targets. Each
# target's own cadence is sources.crawl_interval_seconds (sección 5.1).
TICK_INTERVAL_SECONDS = int(os.getenv("TICK_INTERVAL_SECONDS", "300"))
# Pause between two targets of the same source (randomized in [x/2, x]).
CRAWL_JITTER_SECONDS = float(os.getenv("CRAWL_JITTER_SECONDS", "8"))
# Enrichment of matched listings (sección 5.5) and the watchlist refresher
# (sección 5.6) wake up this often; each listing is checked at most daily.
ENRICH_TICK_SECONDS = int(os.getenv("ENRICH_TICK_SECONDS", "300"))
WATCHLIST_TICK_SECONDS = int(os.getenv("WATCHLIST_TICK_SECONDS", "3600"))
# Recommended listings whose `published_at` is older than this are dropped.
# When the source doesn't expose a date, only the seen set (matches) + bootstrap apply.
RECOMMENDED_MAX_AGE_DAYS = int(os.getenv("RECOMMENDED_MAX_AGE_DAYS", "15"))

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

# Sources offered by the Telegram wizard (the enabled ones live in the sources table).
SOURCES = ["mercadolibre", "facebook", "v6", "kavak", "autocosmos"]

# Notifications (sección 7). The email channel is on when both are set.
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()
# The web (web/, Next.js): base of the tracked links /r/<notification_id>
# (sección 7.3), which the web serves, and of the links the bot sends. Empty:
# alert links go straight to the listing, untracked.
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "").strip().rstrip("/")
# The queue of immediate notifications is drained after every crawl batch and
# also this often (retries, rows queued by other loops).
NOTIFY_TICK_SECONDS = int(os.getenv("NOTIFY_TICK_SECONDS", "60"))

# LLM layer (sección 8): the assisted mode's parser. `claude_cli` runs
# `claude -p` on this host (Claude Code installed and logged in); `local` is an
# OpenAI-compatible server (Ollama, llama.cpp) for the launch.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude_cli").strip().lower()
# Empty: `claude` from PATH. On Windows point it at claude.exe (a .cmd shim
# can't run without a shell).
CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", "").strip()
CLAUDE_CLI_MODEL = os.getenv("CLAUDE_CLI_MODEL", "haiku").strip()
# Budget for one job, retry included (the web gives up a bit after this).
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1").strip()
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "").strip()
# How often an idle llm_jobs loop looks for queued jobs, and how many jobs run
# at once (each one is a `claude -p` process).
LLM_POLL_SECONDS = float(os.getenv("LLM_POLL_SECONDS", "2"))
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "1"))
