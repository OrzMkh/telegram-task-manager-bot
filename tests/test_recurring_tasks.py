import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from task_detector import is_recurring_task_message, clean_recurring_task_text, is_task_message
from task_database import init_db, add_recurring_task, get_all_recurring_tasks, rate_recurring_task, get_recurring_evaluations, delete_recurring_task


class TestRecurringTasks(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_tasks.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        init_db(self.test_db)

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_detector_triggers(self):
        self.assertTrue(is_recurring_task_message("ЗП Проверить кассу"))
        self.assertTrue(is_recurring_task_message("зп Еженедельный аудит"))
        self.assertTrue(is_recurring_task_message("ZP Weekly audit"))
        self.assertTrue(is_recurring_task_message("zp: Проверка байков"))
        self.assertTrue(is_recurring_task_message("ЗП. Проверка парка"))

        # Regular SLA tasks should not trigger recurring
        self.assertFalse(is_recurring_task_message("З Сделать отчет"))
        self.assertFalse(is_recurring_task_message("Задача: проверить"))

        # Recurring task text should not trigger regular SLA task
        self.assertFalse(is_task_message("ЗП Проверить кассу"))
        self.assertFalse(is_task_message("zp Еженедельный аудит"))

    def test_clean_text(self):
        self.assertEqual(clean_recurring_task_text("ЗП Проверить кассу"), "Проверить кассу")
        self.assertEqual(clean_recurring_task_text("zp: Еженедельный аудит"), "Еженедельный аудит")
        self.assertEqual(clean_recurring_task_text("ЗП - Аудит парка"), "Аудит парка")

    def test_database_crud_and_rating(self):
        # 1. Add recurring task
        t = add_recurring_task(
            title="Еженедельный аудит парка",
            assignee="@isslamov",
            author="@orzmkh",
            frequency="Раз в неделю",
            day_of_week="Пн",
            created_at="2026-08-11 20:00:00",
            message_link="https://t.me/c/123/456",
            db_path=self.test_db
        )
        self.assertIsNotNone(t.get("id"))
        task_id = t["id"]

        # 2. Get list
        tasks = get_all_recurring_tasks(db_path=self.test_db)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "Еженедельный аудит парка")
        self.assertEqual(tasks[0]["assignee"], "@isslamov")
        self.assertEqual(tasks[0]["day_of_week"], "Пн")

        # 3. Rate task for period
        rated = rate_recurring_task(task_id, rating=5, comment="Отлично выполнено", evaluated_at="2026-08-11 20:30:00", db_path=self.test_db)
        self.assertEqual(rated["last_rating"], 5)
        self.assertEqual(rated["last_rating_comment"], "Отлично выполнено")

        # 4. Check evaluations history
        evals = get_recurring_evaluations(month="2026-08", db_path=self.test_db)
        self.assertEqual(len(evals), 1)
        self.assertEqual(evals[0]["rating"], 5)
        self.assertEqual(evals[0]["period_month"], "2026-08")

        # 5. Delete task
        deleted = delete_recurring_task(task_id, db_path=self.test_db)
        self.assertTrue(deleted)
        active_tasks = get_all_recurring_tasks(db_path=self.test_db, status="Active")
        self.assertEqual(len(active_tasks), 0)

if __name__ == "__main__":
    unittest.main()
