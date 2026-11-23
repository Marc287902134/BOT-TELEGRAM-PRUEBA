import os
from dotenv import load_dotenv

load_dotenv()

def _csv_ints(value: str):
    return {int(x.strip()) for x in value.split(",") if x.strip()}

class Settings:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    allowed_user_ids = _csv_ints(os.getenv("TELEGRAM_ALLOWED_USER_IDS", ""))
    hubspot_token = os.getenv("HUBSPOT_TOKEN", "")
    hubspot_base = os.getenv("HUBSPOT_API_BASE", "https://api.hubapi.com").rstrip("/")
    ai_key = os.getenv("AI_API_KEY", "")
    ai_base = os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1")
    ai_model = os.getenv("AI_MODEL", "openai/gpt-oss-20b")
    timezone = os.getenv("TIMEZONE", "Europe/Madrid")
    poll_interval = int(os.getenv("POLL_INTERVAL", "60"))
    daily_summary_time = os.getenv("DAILY_SUMMARY_TIME", "09:00")
    task_reminder_minutes = int(os.getenv("TASK_REMINDER_MINUTES", "60"))
    currency = os.getenv("CURRENCY", "EUR")
    database_path = os.getenv("DATABASE_PATH", "agent.db")
    log_level = os.getenv("LOG_LEVEL", "INFO")
    confirm_deletes = os.getenv("CONFIRM_DELETES", "true").lower() == "true"
    confirm_deal_stage_changes = os.getenv("CONFIRM_DEAL_STAGE_CHANGES", "true").lower() == "true"
    events = {x.strip() for x in os.getenv("EVENTS", "contacts,companies,deals,tickets,tasks").split(",") if x.strip()}

settings = Settings()

def validate_settings():
    missing = []
    for key, value in [
        ("TELEGRAM_BOT_TOKEN", settings.telegram_token),
        ("TELEGRAM_ALLOWED_USER_IDS", settings.allowed_user_ids),
        ("HUBSPOT_TOKEN", settings.hubspot_token),
        ("AI_API_KEY", settings.ai_key),
    ]:
        if not value:
            missing.append(key)
    if missing:
        raise RuntimeError("Faltan variables obligatorias: " + ", ".join(missing))
