import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Settings
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", "-1002638798110")

# Google Sheets Settings
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "14lJVvDmK9LOAERAo9twp3Ak-FEdvlrzu-8FywP2dTn4")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")

# Database & System Settings
DB_PATH = os.getenv("DB_PATH", "tasks.db")
SLA_CHECK_INTERVAL = int(os.getenv("SLA_CHECK_INTERVAL", "30"))

# Timezone (Tashkent UTC+5)
from datetime import datetime, timedelta, timezone
TIMEZONE_OFFSET = timezone(timedelta(hours=5))

def get_now() -> datetime:
    return datetime.now(TIMEZONE_OFFSET).replace(tzinfo=None)

