import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Runtime files (.env, Playwright sessions) live at the repo root, as before
# the move to worker/.
ROOT = Path(__file__).resolve().parent.parent

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
# Operational alerts (sección 10): a collector that keeps failing, and its
# recovery. Empty: no alerts (the admin still sees it in /admin/sources).
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()
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

# LLM layer (sección 8): OpenAI Luna for the assisted parser; the Claude
# providers remain available. `local` is an OpenAI-compatible server stub.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna").strip()
# Empty: `claude` from PATH. On Windows point it at claude.exe (a .cmd shim
# can't run without a shell).
CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", "").strip()
CLAUDE_CLI_MODEL = os.getenv("CLAUDE_CLI_MODEL", "haiku").strip()
# Budget for one job, retry included (the web gives up a bit after this).
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
# LLM_PROVIDER=anthropic (F7, punto 6): the Claude API with an API key.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5").strip()
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1").strip()
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "").strip()
# How often an idle llm_jobs loop looks for queued jobs, and how many jobs run
# at once (API calls, or `claude -p` processes for the CLI provider).
LLM_POLL_SECONDS = float(os.getenv("LLM_POLL_SECONDS", "2"))
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "1"))

# Operation (F7, punto 8). Log file with daily rotation (empty: stdout only),
# how often the worker writes its heartbeat, and when tools/watchdog.py
# considers it dead.
LOG_FILE = os.getenv("LOG_FILE", str(ROOT / "logs" / "worker.log")).strip()
LOG_KEEP_DAYS = int(os.getenv("LOG_KEEP_DAYS", "14"))
HEARTBEAT_SECONDS = int(os.getenv("HEARTBEAT_SECONDS", "60"))
WATCHDOG_STALE_MINUTES = int(os.getenv("WATCHDOG_STALE_MINUTES", "10"))


def startup_warnings(env: dict | None = None, which=None) -> list[str]:
    """What this configuration leaves off (F7, punto 5): one line per channel,
    metric or feature that won't work. main.py logs them as WARNING."""
    import shutil

    g = globals() if env is None else env
    which = which or shutil.which
    out = []
    base = g["WEB_BASE_URL"]
    if not base:
        out.append("sin WEB_BASE_URL: los links de las alertas van directo a la publicación, "
                   "sin /r/<id>; no se miden aperturas ni clics (§53) y no hay «Ver en Automotive»")
    elif not base.startswith("https://"):
        out.append("WEB_BASE_URL no es https: Telegram no muestra el botón «Ver en Automotive»")
    if not (g["RESEND_API_KEY"] and g["EMAIL_FROM"]):
        out.append("email desactivado: faltan RESEND_API_KEY / EMAIL_FROM (canal obligatorio del §21)")
    if g.get("TELEGRAM_ENABLED", False) and not g["TELEGRAM_ADMIN_CHAT_ID"]:
        out.append("alertas operativas desactivadas: falta TELEGRAM_ADMIN_CHAT_ID")
    if g["LLM_PROVIDER"] == "claude_cli":
        out.append("LLM_PROVIDER=claude_cli usa tu suscripción de Claude Code: para usuarios del piloto, "
                   "LLM_PROVIDER=openai con OPENAI_API_KEY o anthropic con ANTHROPIC_API_KEY")
        if not which(g["CLAUDE_CLI_PATH"] or "claude"):
            out.append("no se encontró el CLI de Claude Code (CLAUDE_CLI_PATH): "
                       "el modo asistido cae siempre al formulario")
    elif g["LLM_PROVIDER"] == "anthropic":
        if not g.get("ANTHROPIC_API_KEY"):
            out.append("LLM_PROVIDER=anthropic sin ANTHROPIC_API_KEY: el modo asistido cae siempre al formulario")
    elif g["LLM_PROVIDER"] == "openai":
        if not g.get("OPENAI_API_KEY"):
            out.append("LLM_PROVIDER=openai sin OPENAI_API_KEY: el modo asistido cae siempre al formulario")
    elif g["LLM_PROVIDER"] == "local":
        out.append("LLM_PROVIDER=local todavía es un stub: el modo asistido cae siempre al formulario")
    if not g["GEOCODING_ENABLED"]:
        out.append("geocodificación desactivada: el radio de las búsquedas queda sin verificar")
    return out
