import asyncio
import logging
import sys
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, PrefixHandler, MessageHandler, CallbackQueryHandler, filters

from config import BOT_TOKEN, DB_PATH
from task_database import init_db
from task_sheets_sync import SheetsSyncManager
from task_handlers import (
    start_handler,
    task_command_handler,
    my_tasks_handler,
    list_tasks_handler,
    done_task_handler,
    message_auto_detector_handler,
    dispute_callback_handler,
    dispute_reason_input_handler,
    delete_task_callback_handler,
    rate_task_callback_handler,
    assign_callback_handler,
    recurring_task_callback_handler,
    set_sheets_sync,
    sla_preset_callback_handler,
    sla_cal_init_callback_handler,
    cal_nav_callback_handler,
    cal_day_callback_handler,
    cal_time_callback_handler,
    cal_ignore_callback_handler,
    sla_back_callback_handler,
    complete_task_early_callback_handler,
)

from task_report_handler import (
    bike_report_conversation_handler,
    list_reports_handler,
)
from task_scheduler import check_sla_loop

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def post_init(application):
    # Ensure webhook is cleared if bot was previously set to webhook mode
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Cleared any existing webhooks for clean polling.")
    except Exception as e:
        logger.warning(f"Could not clear webhook: {e}")

    # Launch background SLA checking task
    asyncio.create_task(check_sla_loop(application, db_path=DB_PATH, sheets_sync=application.bot_data.get("sheets_sync")))
    logger.info("Background SLA monitor task launched.")

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK - Bot is running")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()

    def log_message(self, format, *args):
        pass

def start_health_server():
    port = int(os.getenv("PORT", "8080"))
    HTTPServer.allow_reuse_address = True
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info(f"Health check HTTP server running on port {port}.")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Failed to start health check server on port {port}: {e}")

def main():
    # Start lightweight health check HTTP server for Render / Cloud hosting
    threading.Thread(target=start_health_server, daemon=True).start()

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in environment or .env file!")
        print("\n[!] ERROR: BOT_TOKEN is missing. Please set BOT_TOKEN in your environment or .env file.\n")
        sys.exit(1)

    # 1. Initialize SQLite Database
    init_db(DB_PATH)
    logger.info(f"Initialized SQLite database at '{DB_PATH}'.")

    # 2. Initialize Google Sheets Sync
    sheets_sync = SheetsSyncManager()
    set_sheets_sync(sheets_sync)

    # 3. Build Telegram Bot Application
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.bot_data["sheets_sync"] = sheets_sync

    # 4. Register Bike Report Conversation Handler (high priority)
    application.add_handler(bike_report_conversation_handler)

    # 5. Register Command Handlers (ASCII for CommandHandler, Multilingual for PrefixHandler)
    application.add_handler(CommandHandler(["start", "help"], start_handler))
    application.add_handler(CommandHandler(["task", "add", "newtask"], task_command_handler))
    application.add_handler(CommandHandler(["my", "mytasks", "my_tasks"], my_tasks_handler))
    application.add_handler(CommandHandler(["list", "tasks"], list_tasks_handler))
    application.add_handler(CommandHandler(["done", "complete"], done_task_handler))
    application.add_handler(CommandHandler(["reports"], list_reports_handler))

    application.add_handler(PrefixHandler("/", ["start", "help", "помощь"], start_handler))
    application.add_handler(PrefixHandler("/", ["task", "задача", "add"], task_command_handler))
    application.add_handler(PrefixHandler("/", ["my", "mytasks", "my_tasks", "мои", "мои_задачи", "моизадачи"], my_tasks_handler))
    application.add_handler(PrefixHandler("/", ["list", "задачи"], list_tasks_handler))
    application.add_handler(PrefixHandler("/", ["done", "готово", "выполнено"], done_task_handler))
    application.add_handler(PrefixHandler("/", ["reports", "отчеты", "отчёты"], list_reports_handler))

    # 6. Button text handler for "📋 Мои задачи"
    application.add_handler(MessageHandler(filters.Regex(r"^(📋\s*Мои задачи|Мои задачи)$"), my_tasks_handler))

    # 7. Register Dispute, Delete, Assign & Rate Handlers
    application.add_handler(CallbackQueryHandler(delete_task_callback_handler, pattern="^delete_task_"))
    application.add_handler(CallbackQueryHandler(rate_task_callback_handler, pattern="^rate_task_"))
    application.add_handler(CallbackQueryHandler(dispute_callback_handler, pattern="^dispute_task_"))
    application.add_handler(CallbackQueryHandler(assign_callback_handler, pattern="^assign_"))
    application.add_handler(CallbackQueryHandler(recurring_task_callback_handler, pattern="^(recasgn_|recfreq_|recday_|delrec_)"))
    application.add_handler(CallbackQueryHandler(sla_preset_callback_handler, pattern="^sla_preset_"))
    application.add_handler(CallbackQueryHandler(sla_cal_init_callback_handler, pattern="^sla_cal_init_"))
    application.add_handler(CallbackQueryHandler(cal_nav_callback_handler, pattern="^cal_nav_"))
    application.add_handler(CallbackQueryHandler(cal_day_callback_handler, pattern="^cal_day_"))
    application.add_handler(CallbackQueryHandler(cal_time_callback_handler, pattern="^cal_time_"))
    application.add_handler(CallbackQueryHandler(cal_ignore_callback_handler, pattern="^cal_ignore_"))
    application.add_handler(CallbackQueryHandler(sla_back_callback_handler, pattern="^sla_back_"))
    application.add_handler(CallbackQueryHandler(complete_task_early_callback_handler, pattern="^complete_task_early_"))

    # 8. Register Auto-detection Message Handler for non-command messages
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), dispute_reason_input_handler), group=1)
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_auto_detector_handler), group=2)


    # 8. Run Bot with Auto-Retry on Render Deploys
    import time
    logger.info("Telegram Task Manager Bot started. Polling for updates...")
    max_retries = 15
    retry_delay = 5
    for attempt in range(1, max_retries + 1):
        try:
            application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True, close_loop=False)
            break
        except Exception as e:
            if "Conflict" in str(e) or "terminated by other getUpdates" in str(e):
                logger.warning(f"Telegram Conflict (attempt {attempt}/{max_retries}): Previous container shutting down. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Unexpected bot polling error (attempt {attempt}/{max_retries}): {e}")
                time.sleep(retry_delay)

if __name__ == "__main__":
    main()


