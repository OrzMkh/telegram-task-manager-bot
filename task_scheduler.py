import asyncio
import logging
from datetime import datetime, timedelta
from telegram.ext import Application

from task_database import get_all_tasks, mark_reminder_sent, update_task_status
from task_sheets_sync import SheetsSyncManager
from config import TARGET_CHAT_ID, DB_PATH, SLA_CHECK_INTERVAL, get_now

logger = logging.getLogger(__name__)

async def check_sla_loop(app: Application, db_path: str = DB_PATH, sheets_sync: SheetsSyncManager = None):
    logger.info("Started SLA background monitoring loop.")
    while True:
        try:
            now = get_now()
            active_tasks = get_all_tasks(db_path=db_path, status="Active", sheets_sync=sheets_sync)


            for task in active_tasks:
                task_id = task["id"]
                assignee = task["assignee"]
                task_text = task["task_text"]
                sla_str = task["sla_deadline"]

                try:
                    sla_dt = datetime.strptime(sla_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    logger.error(f"Invalid date format for task #{task_id}: {sla_str}")
                    continue

                # 1. Check if 1 hour before SLA (between 0 and 60 minutes left)
                time_until_sla = sla_dt - now
                if timedelta(seconds=0) < time_until_sla <= timedelta(hours=1) and not task["reminder_sent"]:
                    reminder_msg = (
                        f"⏰ <b>НАПОМИНАНИЕ ПО ЗАДАЧЕ #{task_id}</b>\n"
                        f"👤 <b>Исполнитель:</b> {assignee}\n"
                        f"📋 <b>Задача:</b> {task_text}\n"
                        f"⏳ <b>Остался 1 час до SLA!</b> (Срок: {sla_str})"
                    )
                    try:
                        await app.bot.send_message(
                            chat_id=int(TARGET_CHAT_ID),
                            text=reminder_msg,
                            parse_mode="HTML"
                        )
                        mark_reminder_sent(task_id, db_path=db_path)
                        logger.info(f"1-hour SLA reminder sent for task #{task_id}.")
                    except Exception as e:
                        logger.error(f"Failed to send 1-hour SLA reminder for task #{task_id}: {e}")

                # 2. Check if SLA is expired
                elif now >= sla_dt:
                    alert_msg = (
                        f"🚨 <b>ALERT: ЗАДАЧА #{task_id} ПРОСРОЧЕНА!</b>\n"
                        f"👤 <b>Исполнитель:</b> {assignee}\n"
                        f"📋 <b>Задача:</b> {task_text}\n"
                        f"⌛ <b>Срок SLA истёк:</b> {sla_str}"
                    )
                    try:
                        await app.bot.send_message(
                            chat_id=int(TARGET_CHAT_ID),
                            text=alert_msg,
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send SLA expired alert for task #{task_id}: {e}")

                    # Update status in local DB and Google Sheets
                    update_task_status(task_id, "Expired", db_path=db_path)
                    if sheets_sync:
                        sheets_sync.update_task_status(task_id, "Expired")
                    logger.info(f"Task #{task_id} marked as Expired.")

        except Exception as e:
            logger.error(f"Error in SLA monitoring loop: {e}")

        await asyncio.sleep(SLA_CHECK_INTERVAL)
