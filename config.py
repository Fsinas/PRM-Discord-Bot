import os
from dataclasses import dataclass
from dotenv import load_dotenv
from typing import List

load_dotenv()

@dataclass
class RuntimeConfig:
    bot_token: str
    public_channel_id: int
    support_channel_id: int
    log_channel_id: int
    admin_role_ids: List[int]
    escalation_role_id: int | None
    db_path: str
    allow_anon_public: bool
    dm_on_close: bool
    stale_public_days: int
    stale_private_days: int
    reminder_hours: int
    auto_purge_days: int
    max_title_len: int
    ticket_cooldown_seconds: int
    duplicate_similarity: float
    anonymize_public: bool = False
    in_progress_emoji: str = "🛠️"

    def to_dict(self):
        return {
            "anonymize_public": self.anonymize_public,
            "in_progress_emoji": self.in_progress_emoji,
            "duplicate_similarity": self.duplicate_similarity,
            "ticket_cooldown_seconds": self.ticket_cooldown_seconds,
        }

_config: RuntimeConfig | None = None

def load_config() -> RuntimeConfig:
    global _config
    if _config:
        return _config
    _config = RuntimeConfig(
        bot_token = os.getenv("BOT_TOKEN",""),
        public_channel_id = int(os.getenv("PUBLIC_CHANNEL_ID","0")),
        support_channel_id = int(os.getenv("SUPPORT_CHANNEL_ID","0")),
        log_channel_id = int(os.getenv("LOG_CHANNEL_ID","0")),
        admin_role_ids = [int(r.strip()) for r in os.getenv("ADMIN_ROLE_IDS","" ).split(",") if r.strip().isdigit()],
        escalation_role_id = int(os.getenv("ESCALATION_ROLE_ID","0")) or None,
        db_path = os.getenv("DB_PATH","./tickets.db"),
        allow_anon_public = os.getenv("ALLOW_ANON_PUBLIC","0") == "1",
        dm_on_close = os.getenv("DM_ON_CLOSE","1") == "1",
        stale_public_days = int(os.getenv("STALE_PUBLIC_DAYS","10")),
        stale_private_days = int(os.getenv("STALE_PRIVATE_DAYS","7")),
        reminder_hours = int(os.getenv("REMINDER_HOURS","24")),
        auto_purge_days = int(os.getenv("AUTO_PURGE_DAYS","45")),
        max_title_len = int(os.getenv("MAX_TITLE_LEN","90")),
        ticket_cooldown_seconds = int(os.getenv("TICKET_COOLDOWN_SECONDS","120")),
        duplicate_similarity = float(os.getenv("DUPLICATE_SIMILARITY","0.78")),
    )
    return _config

def get_config():
    return load_config()

def update_runtime_config(**kwargs):
    cfg = get_config()
    for k,v in kwargs.items():
        if hasattr(cfg,k):
            setattr(cfg,k,v)