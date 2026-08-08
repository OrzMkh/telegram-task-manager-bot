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
    "Статус",
    "Первоначальная оценка",
    "Причина оспаривания",
    "Итоговая оценка не меняется"
]

import base64
import json

B64_CREDS = (
    "ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsCiAgInByb2plY3RfaWQiOiAiemlwcHktZm9saW8tNDk0NzExLWgwIiwK"
    "ICAicHJpdmF0ZV9rZXlfaWQiOiAiODFlMDFjOWZkZjRmYjJiNmVjNWJiZjA3MDlmOWZlZDVmOWU5OTQxNCIsCiAgInByaXZh"
    "dGVfa2V5IjogIi0tLS0tQkVHSU4gUFJJVkFURSBLRVktLS0tLVxuTUlJRXZRSUJBREFOQmdrcWhraUc5dzBCQVFFRkFBU0NC"
    "S2N3Z2dTakFnRUFBb0lCQVFENVN4L1VrSHQrSXpRSlxudXJZTWMvUnBHRGRiUjhNTTMrYUZxZzZ6ZTYwUzc3eE8yT0Z6RytQ"
    "L1VrVHpTSUFRSmdCQkN0SjZvZHF3WlFvVFxuK3JVZkpkN0djZVlkLzRLdGtOZ0RPZTkrM01jM0xOeFduV3pRSkFYZ0x3SXgz"
    "VTZYYmRxWk9qNWJWckFndnNlaFxucVBvd2Y1UVM1ZW5md2szL2VqY0RwMzBuV0hMVHlnODN6YlVpaDczN21sZTJSUlducFBh"
    "Zm44em5JVXRsUGxSYVxuc1V1ai8rVGpScy9jL0tKR3ArV0xOdmpsU1dad0dsV2NLV1BFbUI3QmhkKzZNUEp1Z244d0VXK255"
    "L2g0NmlCWlxuM2lQemJZTVUwYThydFpYMCtLaDNlbVVqRTB6Slh6RG9RWDR1dHhhc3Eyend2T05qSTlTVjhHNHJCNzRlY3ht"
    "SlxuZkRVejMrSjdBZ01CQUFFQ2dnRUFkOXlKaU9RUkpHUmJ0R1BiL1IvUmY2aGZrVmx2TEdVSkN2SnBrQjJpYVN6d1xuWHY3"
    "RFkxdWhJNVZVUnA3d3lCTGxZMkNITStSWGFDR2tsMWVmNjBNM21qV1FYWk1KSzFldHJOdHh6ZzdzRUJqWFxuTmlRSitnZWY5"
    "WnJVbE5JaDVBZ3pKeUpNY2hFN3JQcmR0Rm94TlJsYVFqM2VWYkl3VzJwUlFrWUpGRjVnRTNpc1xuS3lMcjZVNlA1TjVIS3dz"
    "S096R1JCU3NWMzZuZ2ZyQWtGVzhRNzh2WkIzYjkwa0hBdjF0dFV2ODh2d25BajFOQVxuWWdLRmNPKytWKzliUkRhN2dabks0"
    "RlFxRkVad1Z0bzI2Z3FXWkI5NHdMVUh4SFlTUkhHMVBwOUJpQVp5WFZ5VFxudGVRNXVYaTJhalh0d3I0Q29zMEIxM3MzbTZv"
    "T3hPV2V1Z2FzK1BCSERRS0JnUUQ5YllTNlF2aHZsUUFIVlVFZ1xuMXRHSng1a1BDbGxhZGJyVi9MR1BwWDc1YWJRWG4yVDdp"
    "RVZTNFVjMkhMZVJPbHgwbmFXcDUvMmp1N1J4NDRkWFxudFZLOHYxaXozZDA2RzZSc29oeVpoWU5hWUkvU0djQWpxSDBYeWJN"
    "L1QyVklhcXI2djRPZ1dQczBpcldJaGVqbVxuaDEwaEExNUgvRXFkVytwVUpCL0YrNEZ4UHdLQmdRRDcwdDBUdHloeGN4RnVp"
    "NzFFMFZDaWdMYkE5YlpmQWI5YVxuNnBKMHJTTDcreHM5NUJ0ZzJZSzJDSkZRYnBzQ0tDZkgvRTB0REUyNmJtWjNucHozSFMr"
    "VHNUZEIrVkU1bzhZNFxueXBhTU1Ndi9wcFR5V1FMTkNlWit6b24veUZ6aGZXc1Nla0xjS09IZ24wWlJtaVJEd3JZczd0M0Mx"
    "TzZERFVRdFxuUTN6WnJ4QUR4UUtCZ1FDNkwzL1hwK1FGZGg0elJQczRPUnB3Y3VlTUdUcFVMekk0akJHWFN5cmg2anFaTUUx"
    "c1xuVGswLytxbnFvMlpwbDhyZEVnVG5zcnl4VWZIYnlpRmcycUlTY1RHbDAxWDRudDVKd1QvcHVpRXFnTTZvdUtwa1xuaUNCL0"
    "hYeEhBdm1TSG12SEZIU0xsVlBZNGg5RVViMHR3RDAzUjlZNFpLNGN0YTZPYW91OVZHMWcyUUtCZ0U3aFxueVpDd2NnRy9xcmsz"
    "R3EyZzU2SlBzVytXU0c5UVM5Rzk0dXliZzNidFBLWlJldVlHbkhSTEVNSGlNN29rTy9uZ1xuSllpejd2RTBQZkxBZzZqQXdy"
    "Ti84ckErMmR1MVdwVlZtSDBIbUE5WDdoWlFIWmwrdlc0QllxYjE2MnBTOENSVVxubWZiKzgycDZXZnViempwUGx1TlNXN0w1"
    "SWxGNDZWOUlZYWFLdVBpRkFvR0FZYWdlZlVCYmJLczVmOHhtakhIVFxub3BycTZjYWowNGNnMGtkVmdHOW1ocUtQcFA0YXV3"
    "MDZHWkdxR0xtVDlHaFJwdlArTW1GemE1M3YxYlRIeURRRVxuMS9XalhJbnl4cWkvdnptYnd0SE1vNmdVR0V1UTZzSFJ1OWh5"
    "d0JvOVBkQnNlQlhZaVcwWVlwTElkME5WQmNEUlxuMmFEeDUybG04VEtFbFFYMDdGNXFMdnM9XG4tLS0tLUVORCBQUklWQVRF"
    "IEtFWS0tLS0tXG4iLAogICJjbGllbnRfZW1haWwiOiAidGdib3RodWJAemlwcHktZm9saW8tNDk0NzExLWgwLmlhbS5nc2Vy"
    "dmljZWFjY291bnQuY29tIiwKICAiY2xpZW50X2lkIjogIjEwOTAwNTcyODkwNjg4NzY4NTU1NSIsCiAgImF1dGhfdXJpIjog"
    "Imh0dHBzOi8vYWNjb3VudHMuZ29vZ2xlLmNvbS9vL29hdXRoMi9hdXRoIiwKICAidG9rZW5fdXJpIjogImh0dHBzOi8vb2F1"
    "dGgyLmdvb2dsZWFwaXMuY29tL3Rva2VuIiwKICAiYXV0aF9wcm92aWRlcl94NTA5X2NlcnRfdXJsIjogImh0dHBzOi8vd3d3"
    "Lmdvb2dsZWFwaXMuY29tL29hdXRoMi92MS9jZXJ0cyIsCiAgImNsaWVudF94NTA5X2NlcnRfdXJsIjogImh0dHBzOi8vd3d3"
    "Lmdvb2dsZWFwaXMuY29tL3JvYm90L3YxL21ldGFkYXRhL3g1MDkvdGdib3RodWIlNDB6aXBweS1mb2xpby00OTQ3MTEtaDAu"
    "aWFtLmdzZXJ2aWNlYWNjb3VudC5jb20iLAogICJ1bml2ZXJzZV9kb21haW4iOiAiZ29vZ2xlYXBpcy5jb20iCn0="
)

class SheetsSyncManager:
    def __init__(self, spreadsheet_id=SPREADSHEET_ID, credentials_file=CREDENTIALS_FILE):
        self.spreadsheet_id = spreadsheet_id
        self.credentials_file = credentials_file
        self.client = None
        self.sheet = None
        self.enabled = False
        self._init_sheets()

    def _init_sheets(self):
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

            # Guaranteed fallback: Decode B64_CREDS
            if not creds and B64_CREDS:
                try:
                    decoded = base64.b64decode(B64_CREDS).decode("utf-8")
                    info = json.loads(decoded)
                    creds = Credentials.from_service_account_info(info, scopes=scopes)
                    logger.info("Loaded Google credentials from built-in B64 service account.")
                except Exception as e:
                    logger.error(f"Failed to decode B64 service account: {e}")

            if not creds:
                logger.warning("No Google credentials available. Google Sheets sync is disabled.")
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
            existing_rows = self.sheet.get_all_values()
            next_id = len(existing_rows)
            t_id = task.get("id")
            if not t_id or str(t_id) == "1" and len(existing_rows) > 1:
                t_id = next_id

            row = [
                str(t_id),
                task["task_text"],
                task["assignee"],
                task["author"],
                task["sla_deadline"],
                task["created_at"],
                task["status"]
            ]
            self.sheet.append_row(row)
            logger.info(f"Task #{t_id} appended to Google Sheets.")
        except Exception as e:
            logger.error(f"Error appending task #{task.get('id')} to Google Sheets: {e}")

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

    def update_task_rating(self, task_id: int, rating: int, is_final: bool = False):
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
                col = 10 if is_final else 8
                self.sheet.update_cell(target_row, col, f"{rating}/5")
                logger.info(f"Task #{task_id} rating updated to {rating}/5 in Google Sheets (col {col}).")
        except Exception as e:
            logger.error(f"Error updating task #{task_id} rating in Google Sheets: {e}")

    def update_task_dispute(self, task_id: int, dispute_reason: str):
        if not self.enabled or not self.sheet:
            return
        try:
            id_col_vals = self.sheet.col_values(1)
            target_row = None
            str_id = str(task_id).replace("#", "").strip()
            for idx, val in enumerate(id_col_vals):
                if str(val).replace("#", "").strip() == str_id:
                    target_row = idx + 1
                    break
            if target_row:
                # Column 7 is 'Статус'
                self.sheet.update_cell(target_row, 7, "Disputed")
                # Column 9 is 'Причина оспаривания'
                self.sheet.update_cell(target_row, 9, dispute_reason)
                logger.info(f"Task #{task_id} marked as 'Disputed' with comment in Google Sheets (row {target_row}).")
        except Exception as e:
            logger.error(f"Error updating task #{task_id} dispute in Google Sheets: {e}")

    def delete_task(self, task_id: int) -> bool:
        if not self.enabled or not self.sheet:
            return False
        try:
            id_col_vals = self.sheet.col_values(1)
            str_id = str(task_id).strip()
            for idx, val in enumerate(id_col_vals):
                if str(val).strip() == str_id:
                    target_row = idx + 1
                    # Set Status (Column 7) to 'Удалена' so it is clearly visible in the sheet
                    self.sheet.update_cell(target_row, 7, "Удалена")
                    logger.info(f"Task #{task_id} status updated to 'Удалена' in Google Sheets (row {target_row}).")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error marking task #{task_id} as 'Удалена' in Google Sheets: {e}")
            return False

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

