import os
from dataclasses import dataclass


def _i(name, default):
    try: return int(os.getenv(name, default))
    except Exception: return int(default)


def _f(name, default):
    try: return float(os.getenv(name, default))
    except Exception: return float(default)

@dataclass(frozen=True)
class Config:
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    db_path: str = os.getenv("MARKET_DB_PATH", "market_ai.sqlite3")
    poll_seconds: int = _i("MARKET_POLL_SECONDS", 60)
    alert_score: float = _f("MARKET_ALERT_SCORE", 72)
    cooldown_seconds: int = _i("MARKET_COOLDOWN_SECONDS", 900)
    browser_restart_minutes: int = _i("BROWSER_RESTART_MINUTES", 45)
    browser_max_rss_mb: int = _i("BROWSER_MAX_RSS_MB", 700)

CONFIG = Config()
