import os
import logging
import time
import base64
import json
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
            if not existing_rows:
                self.sheet.insert_row(HEADERS, 1)
                logger.info("Initialized Google Sheet headers.")
            elif len(existing_rows[0]) < len(HEADERS):
                for col_idx, header_val in enumerate(HEADERS, start=1):
                    if col_idx > len(existing_rows[0]) or existing_rows[0][col_idx - 1] != header_val:
                        try:
                            self.sheet.update_cell(1, col_idx, header_val)
                        except Exception:
                            pass

            self.enabled = True
            logger.info("Google Sheets integration successfully enabled.")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
            self.enabled = False


    def get_all_tasks(self) -> list[dict]:
        if not self.enabled or not self.sheet:
            return []

        now = time.time()
        if hasattr(self, "_tasks_cache") and hasattr(self, "_tasks_cache_time"):
            if now - self._tasks_cache_time < 5 and self._tasks_cache:
                return self._tasks_cache

        try:
            rows = self.sheet.get_all_values()
            if not rows or len(rows) <= 1:
                return []

            headers = [str(h).strip() for h in rows[0]]
            id_idx = headers.index("ID Задачи") if "ID Задачи" in headers else 0
            text_idx = headers.index("Текст задачи") if "Текст задачи" in headers else 1
            ass_idx = headers.index("Исполнитель") if "Исполнитель" in headers else 2
            aut_idx = headers.index("Постановщик") if "Постановщик" in headers else 3
            sla_idx = headers.index("Срок / SLA") if "Срок / SLA" in headers else 4
            date_idx = headers.index("Дата создания") if "Дата создания" in headers else 5
            stat_idx = headers.index("Статус") if "Статус" in headers else 6
            link_idx = headers.index("Ссылка на сообщение") if "Ссылка на сообщение" in headers else (headers.index("Ссылка") if "Ссылка" in headers else 10)

            tasks = []
            for r in rows[1:]:
                if not any(str(cell).strip() for cell in r):
                    continue
                try:
                    task_id = int(str(r[id_idx]).replace("#", "").strip()) if len(r) > id_idx else len(tasks) + 1
                except Exception:
                    continue

                msg_link = r[link_idx] if len(r) > link_idx else ""

                tasks.append({
                    "id": task_id,
                    "task_text": r[text_idx] if len(r) > text_idx else "",
                    "assignee": r[ass_idx] if len(r) > ass_idx else "",
                    "author": r[aut_idx] if len(r) > aut_idx else "",
                    "sla_deadline": r[sla_idx] if len(r) > sla_idx else "",
                    "created_at": r[date_idx] if len(r) > date_idx else "",
                    "status": r[stat_idx] if len(r) > stat_idx else "Active",
                    "message_link": msg_link
                })

            self._tasks_cache = tasks
            self._tasks_cache_time = now
            return tasks
        except Exception as e:
            logger.error(f"Error fetching tasks from Google Sheet: {e}")
            if hasattr(self, "_tasks_cache"):
                return self._tasks_cache
            return []

    def append_task(self, task: dict):
        if not self.enabled or not self.sheet:
            return None
        try:
            # Determine true sequential ID by finding max numeric ID in Column 1
            col1 = self.sheet.col_values(1)
            max_id = 0
            for val in col1[1:]:
                try:
                    num = int(str(val).replace("#", "").strip())
                    if num > max_id:
                        max_id = num
                except Exception:
                    pass
            next_id = max_id + 1
            task["id"] = next_id

            row = [
                str(next_id),
                task.get("task_text", ""),
                task.get("assignee", ""),
                task.get("author", ""),
                task.get("sla_deadline", ""),
                task.get("created_at", ""),
                task.get("status", "Active"),
                "",
                "",
                "",
                task.get("message_link", "")
            ]
            self.sheet.append_row(row)
            logger.info(f"Task #{next_id} appended to Google Sheets.")
            return next_id

        except Exception as e:
            logger.error(f"Error appending task #{task.get('id')} to Google Sheets: {e}")
            return None

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
                self.sheet.update_cell(target_row, col, str(rating))
                logger.info(f"Task #{task_id} rating updated to {rating} in Google Sheets (col {col}).")
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

    def append_recurring_task(self, task: dict):
        if not self.enabled or not self.client:
            return
        try:
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            try:
                sheet = spreadsheet.worksheet("Постоянные задачи")
            except Exception:
                sheet = spreadsheet.add_worksheet(title="Постоянные задачи", rows=500, cols=12)
                headers = [
                    "ID Задачи", "Название задачи", "Исполнитель", "Постановщик",
                    "Частота", "День недели", "Дата создания", "Последняя оценка",
                    "Комментарий к оценке", "Статус", "Ссылка на сообщение"
                ]
                sheet.insert_row(headers, 1)

            existing = sheet.get_all_values()
            if not existing:
                headers = [
                    "ID Задачи", "Название задачи", "Исполнитель", "Постановщик",
                    "Частота", "День недели", "Дата создания", "Последняя оценка",
                    "Комментарий к оценке", "Статус", "Ссылка на сообщение"
                ]
                sheet.insert_row(headers, 1)

            row = [
                task.get("id", ""),
                task.get("title", ""),
                task.get("assignee", ""),
                task.get("author", "Руководитель"),
                task.get("frequency", ""),
                task.get("day_of_week", ""),
                task.get("created_at", ""),
                task.get("last_rating", 0),
                task.get("last_rating_comment", ""),
                task.get("status", "Active"),
                task.get("message_link", "")
            ]
            sheet.append_row(row)
            logger.info(f"Recurring task #{task.get('id')} appended to Google Sheets ('Постоянные задачи').")
        except Exception as e:
            logger.error(f"Error appending recurring task #{task.get('id')} to Google Sheets: {e}")

    def get_all_recurring_tasks(self) -> list[dict]:
        if not self.enabled or not self.client:
            return []
        try:
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            try:
                sheet = spreadsheet.worksheet("Постоянные задачи")
            except Exception:
                return []
            rows = sheet.get_all_values()
            if not rows or len(rows) <= 1:
                return []
            headers = [str(h).strip() for h in rows[0]]
            tasks = []
            for r in rows[1:]:
                if not any(str(cell).strip() for cell in r):
                    continue
                if str(r[0]).strip().startswith("ID"):
                    continue
                tasks.append({
                    "id": r[0] if len(r) > 0 else "",
                    "title": r[1] if len(r) > 1 else "",
                    "assignee": r[2] if len(r) > 2 else "",
                    "author": r[3] if len(r) > 3 else "",
                    "frequency": r[4] if len(r) > 4 else "",
                    "day_of_week": r[5] if len(r) > 5 else "",
                    "created_at": r[6] if len(r) > 6 else "",
                    "last_rating": int(r[7]) if len(r) > 7 and str(r[7]).isdigit() else 0,
                    "last_rating_comment": r[8] if len(r) > 8 else "",
                    "status": r[9] if len(r) > 9 else "Active",
                    "message_link": r[10] if len(r) > 10 else ""
                })
            return tasks
        except Exception as e:
            logger.error(f"Failed to fetch recurring tasks from Google Sheets: {e}")
            return []


