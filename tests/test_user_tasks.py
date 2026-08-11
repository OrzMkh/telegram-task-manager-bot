import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from task_database import init_db, add_task, update_task_status, get_user_tasks

TEST_DB = "test_tasks.db"

def test_task_filtering():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
        
    init_db(TEST_DB)
    
    # 1. Add tasks
    t1 = add_task("Собрать байки на Юнусабаде", "@isslamov", "@orzmkh", "2026-08-12 18:00:00", "2026-08-11 12:00:00", db_path=TEST_DB)
    t2 = add_task("Проверить баланс кассы", "@axi0603", "@orzmkh", "2026-08-12 19:00:00", "2026-08-11 12:00:00", db_path=TEST_DB)
    t3 = add_task("Общий созвон команды", "Вся команда", "@orzmkh", "2026-08-12 20:00:00", "2026-08-11 12:00:00", db_path=TEST_DB)
    t4 = add_task("Завершенная задача", "@isslamov", "@orzmkh", "2026-08-11 15:00:00", "2026-08-11 10:00:00", db_path=TEST_DB)
    
    # Mark t4 as Completed
    update_task_status(t4["id"], "Completed", db_path=TEST_DB)
    
    # Check tasks for isslamov
    isslamov_tasks = get_user_tasks("@isslamov", status="Active", db_path=TEST_DB)
    assert len(isslamov_tasks) == 2, f"Expected 2 tasks for isslamov (t1 + team), got {len(isslamov_tasks)}"
    task_ids = [t["id"] for t in isslamov_tasks]
    assert t1["id"] in task_ids, "t1 must be present"
    assert t3["id"] in task_ids, "team task t3 must be present"
    assert t4["id"] not in task_ids, "Completed task t4 must NOT be present"
    assert t2["id"] not in task_ids, "axi0603 task t2 must NOT be present"
    
    # Check tasks for axi0603 by Russian name "Мужохид"
    mujahed_tasks = get_user_tasks("Мужохид", status="Active", db_path=TEST_DB)
    assert len(mujahed_tasks) == 2, f"Expected 2 tasks for Мужохид, got {len(mujahed_tasks)}"
    
    # Check Expired tasks (still active until completed)
    t5 = add_task("Просроченная задача", "@axi0603", "@orzmkh", "2026-08-10 10:00:00", "2026-08-09 10:00:00", db_path=TEST_DB)
    update_task_status(t5["id"], "Expired", db_path=TEST_DB)
    
    axi_tasks_with_expired = get_user_tasks("axi0603", status="Active", db_path=TEST_DB)
    assert len(axi_tasks_with_expired) == 3, f"Expected 3 tasks (t2 + team + t5), got {len(axi_tasks_with_expired)}"
    assert t5["id"] in [t["id"] for t in axi_tasks_with_expired]

    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_task_filtering()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
