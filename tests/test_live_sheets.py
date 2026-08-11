import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from task_sheets_sync import SheetsSyncManager
from task_database import get_user_tasks, get_all_tasks

sheets_sync = SheetsSyncManager()

print("--- ALL ACTIVE TASKS FROM GOOGLE SHEETS ---")
all_t = get_all_tasks(sheets_sync=sheets_sync, status="Active")
for t in all_t:
    print(f"#{t['id']} | Assignee: {t['assignee']} | Status: {t['status']} | Text: {t['task_text']}")

print("\n--- TASKS FOR @axi0603 (Мужохид) ---")
axi_t = get_user_tasks("@axi0603", sheets_sync=sheets_sync, status="Active")
for t in axi_t:
    print(f"#{t['id']} | Assignee: {t['assignee']} | Text: {t['task_text']}")

print("\n--- TASKS FOR @isslamov (Ильясбек) ---")
iss_t = get_user_tasks("@isslamov", sheets_sync=sheets_sync, status="Active")
for t in iss_t:
    print(f"#{t['id']} | Assignee: {t['assignee']} | Text: {t['task_text']}")
