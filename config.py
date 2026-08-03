import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Settings
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", "-1002638798110")

# Google Sheets Settings
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "14lJVvDmK9LOAERAo9twp3Ak-FEdvlrzu-8FywP2dTn4")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")

# Database & System Settings
DB_PATH = os.getenv("DB_PATH", "tasks.db")
SLA_CHECK_INTERVAL = int(os.getenv("SLA_CHECK_INTERVAL", "30"))
