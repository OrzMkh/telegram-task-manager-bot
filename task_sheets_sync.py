import os
import logging
from config import SPREADSHEET_ID, CREDENTIALS_FILE

logger = logging.getLogger(__name__)

HEADERS = [
    "ID Задачи",
    "Текст задачи",
    "Исполнитель",
    "Постановщик",
    "Срок / SLA",
    "Дата создания",
    "Статус"
]

class SheetsSyncManager:
    def __init__(self, spreadsheet_id=SPREADSHEET_ID, credentials_file=CREDENTIALS_FILE):
        self.spreadsheet_id = spreadsheet_id
        self.credentials_file = credentials_file
        self.client = None
        self.sheet = None
        self.enabled = False
        self._init_sheets()

    def _init_sheets(self):
        import json
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = None
            creds_json_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
            if creds_json_env:
                try:
                    s_clean = creds_json_env.strip()
                    if (s_clean.startswith("'") and s_clean.endswith("'")) or (s_clean.startswith('"') and s_clean.endswith('"')):
                        s_clean = s_clean[1:-1].strip()
                    info = json.loads(s_clean)
                    if isinstance(info.get("private_key"), str):
                        info["private_key"] = info["private_key"].replace("\\n", "\n")
                    creds = Credentials.from_service_account_info(info, scopes=scopes)
                    logger.info("Loaded Google credentials from GOOGLE_CREDENTIALS_JSON env var.")
                except Exception as e:
                    logger.error(f"Failed to parse GOOGLE_CREDENTIALS_JSON: {e}")

            if not creds and os.path.exists(self.credentials_file):
                creds = Credentials.from_service_account_file(self.credentials_file, scopes=scopes)

            if not creds:
                logger.warning(f"Google Sheets credentials file '{self.credentials_file}' or GOOGLE_CREDENTIALS_JSON env var not found. Google Sheets sync is disabled.")
                self.enabled = False
                return

            self.client = gspread.authorize(creds)

            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            self.sheet = spreadsheet.sheet1

            # Check if headers exist
            existing_rows = self.sheet.get_all_values()
            if not existing_rows or existing_rows[0] != HEADERS:
                self.sheet.insert_row(HEADERS, 1)
                logger.info("Initialized Google Sheet headers.")

            self.enabled = True
            logger.info("Google Sheets integration successfully enabled.")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
            self.enabled = False

    def append_task(self, task: dict):
        if not self.enabled or not self.sheet:
            return
        try:
            row = [
                task["id"],
                task["task_text"],
                task["assignee"],
                task["author"],
                task["sla_deadline"],
                task["created_at"],
                task["status"]
            ]
            self.sheet.append_row(row)
            logger.info(f"Task #{task['id']} appended to Google Sheets.")
        except Exception as e:
            logger.error(f"Error appending task #{task['id']} to Google Sheets: {e}")

    def update_task_status(self, task_id: int, new_status: str):
        if not self.enabled or not self.sheet:
            return
        try:
            cell = self.sheet.find(str(task_id), in_column=1)
            if cell:
                # Column 7 is 'Статус'
                self.sheet.update_cell(cell.row, 7, new_status)
                logger.info(f"Task #{task_id} status updated to {new_status} in Google Sheets.")
            else:
                logger.warning(f"Task #{task_id} not found in Google Sheets for status update.")
        except Exception as e:
            logger.error(f"Error updating task #{task_id} status in Google Sheets: {e}")

    def update_task_rating(self, task_id: int, rating: int):
        if not self.enabled or not self.sheet:
            return
        try:
            id_col_vals = self.sheet.col_values(1)
            target_row = None
            str_id = str(task_id).strip()
            for idx, val in enumerate(id_col_vals):
                if str(val).strip() == str_id:
                    target_row = idx + 1
                    break
            if target_row:
                self.sheet.update_cell(target_row, 8, f"{rating}/5")
                logger.info(f"Task #{task_id} rating updated to {rating}/5 in Google Sheets.")
        except Exception as e:
            logger.error(f"Error updating task #{task_id} rating in Google Sheets: {e}")

    def update_task_dispute(self, task_id: int, dispute_reason: str):
        if not self.enabled or not self.sheet:
            return
        try:
            id_col_vals = self.sheet.col_values(1)
            target_row = None
            str_id = str(task_id).strip()
            for idx, val in enumerate(id_col_vals):
                if str(val).strip() == str_id:
                    target_row = idx + 1
                    break
            if target_row:
                self.sheet.update_cell(target_row, 9, f"Оспаривание: {dispute_reason}")
                logger.info(f"Task #{task_id} dispute comment updated in Google Sheets.")
        except Exception as e:
            logger.error(f"Error updating task #{task_id} dispute in Google Sheets: {e}")

    def append_bike_report(self, report: dict):
        if not self.enabled or not self.client:
            return
        try:
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            # Try to get or create worksheet "Байки"
            try:
                sheet = spreadsheet.worksheet("Байки")
            except Exception:
                sheet = spreadsheet.add_worksheet(title="Байки", rows=1000, cols=20)
                headers = [
                    "ID", "Дата", "Выдано", "Вернули", "Всего в поездке",
                    "Новые байки", "Старые байки", "Сломанные",
                    "Причины возврата", "Комментарий", "Партнёр", "Время отправки"
                ]
                sheet.insert_row(headers, 1)

            # Ensure headers if worksheet was empty
            existing = sheet.get_all_values()
            if not existing:
                headers = [
                    "ID", "Дата", "Выдано", "Вернули", "Всего в поездке",
                    "Новые байки", "Старые байки", "Сломанные",
                    "Причины возврата", "Комментарий", "Партнёр", "Время отправки"
                ]
                sheet.insert_row(headers, 1)

            row = [
                report.get("id", ""),
                report.get("report_date", ""),
                report.get("issued", ""),
                report.get("returned", ""),
                report.get("total_in_trip", ""),
                report.get("new_bikes", ""),
                report.get("old_bikes", ""),
                report.get("broken_bikes", ""),
                report.get("return_reasons", ""),
                report.get("comment", ""),
                report.get("username", ""),
                report.get("created_at", "")
            ]
            sheet.append_row(row)
            logger.info(f"Bike report #{report.get('id')} appended to Google Sheets ('Байки').")
        except Exception as e:
            logger.error(f"Error appending bike report #{report.get('id')} to Google Sheets: {e}")

