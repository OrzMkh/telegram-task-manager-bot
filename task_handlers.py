import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from task_database import add_task, get_all_tasks, get_task, update_task_status
from task_sheets_sync import SheetsSyncManager
from task_detector import (
    is_task_message,
    extract_assignee,
    extract_author,
    parse_sla_deadline,
    clean_task_text
)
from config import DB_PATH

logger = logging.getLogger(__name__)

sheets_sync_instance: SheetsSyncManager | None = None

def set_sheets_sync(manager: SheetsSyncManager):
    global sheets_sync_instance
    sheets_sync_instance = manager


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import ReplyKeyboardMarkup
    help_text = (
        "🤖 <b>Telegram Бот-Менеджер Задач и Отчётов для Партнёров («Байки»)</b>\n\n"
        "<b>📝 Форма отчёта партнеров:</b>\n"
        "• <code>/report</code> или <code>/байки</code> — Заполнить ежедневный отчёт по байкам.\n"
        "• <code>/reports</code> — Просмотреть последние отправленные отчёты.\n\n"
        "<b>📌 Управление задачами:</b>\n"
        "• <code>/task &lt;текст&gt;</code> или <code>/задача &lt;текст&gt;</code> — Поставить задачу.\n"
        "• <code>/list</code> или <code>/задачи</code> — Список активных задач.\n"
        "• <code>/done &lt;ID&gt;</code> — Завершить задачу.\n"
        "• <code>/help</code> — Справка."
    )
    keyboard = ReplyKeyboardMarkup(
        [["📝 Заполнить отчёт (Байки)"], ["/list", "/reports"]],
        resize_keyboard=True
    )
    await update.message.reply_text(help_text, parse_mode="HTML", reply_markup=keyboard)



async def task_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text or ""
    task_raw_text = clean_task_text(text)

    if not task_raw_text or task_raw_text.lower() in ["/task", "/задача", "/add"]:
        await update.message.reply_text("⚠️ Пожалуйста, укажите текст задачи после команды. Пример: <code>/task Подготовить отчёт</code>", parse_mode="HTML")
        return

    await _process_and_create_task(update, task_raw_text)


async def list_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active_tasks = get_all_tasks(db_path=DB_PATH, status="Active")
    if not active_tasks:
        await update.message.reply_text("📌 На данный момент нет активных задач.")
        return

    msg = "📋 <b>АКТИВНЫЕ ЗАДАЧИ:</b>\n\n"
    for t in active_tasks:
        msg += (
            f"🔹 <b>#{t['id']}</b> — {t['task_text']}\n"
            f"👤 <b>Исполнитель:</b> {t['assignee']} | ✍️ <b>Автор:</b> {t['author']}\n"
            f"⏰ <b>SLA:</b> {t['sla_deadline']}\n\n"
        )
    await update.message.reply_text(msg, parse_mode="HTML")


async def done_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Использование: <code>/done &lt;ID задачи&gt;</code> (например, <code>/done 1</code>)", parse_mode="HTML")
        return

    task_id_str = context.args[0].replace("#", "")
    if not task_id_str.isdigit():
        await update.message.reply_text("⚠️ Пожалуйста, укажите числовой ID задачи.")
        return

    task_id = int(task_id_str)
    task = get_task(task_id, db_path=DB_PATH)

    if not task:
        await update.message.reply_text(f"❌ Задача #{task_id} не найдена.")
        return

    if task["status"] == "Completed":
        await update.message.reply_text(f"ℹ️ Задача #{task_id} уже выполнена!")
        return

    update_task_status(task_id, "Completed", db_path=DB_PATH)
    if sheets_sync_instance:
        sheets_sync_instance.update_task_status(task_id, "Completed")

    await update.message.reply_text(f"🎉 <b>Задача #{task_id} отмечена как выполненная!</b>", parse_mode="HTML")


async def message_auto_detector_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.message.from_user
    if not user:
        return

    text = update.message.text

    # Skip if message starts with a command registered elsewhere (e.g. /start, /help, /list, /done)
    if text.startswith("/") and not any(text.startswith(cmd) for cmd in ["/task", "/задача", "/add"]):
        return

    if is_task_message(text, user=user):
        task_text = clean_task_text(text)
        await _process_and_create_task(update, task_text)


async def _process_and_create_task(update: Update, task_text: str):
    message = update.message
    assignee = extract_assignee(message)
    author = extract_author(message)
    
    now = datetime.now()
    created_at_str = now.strftime("%Y-%m-%d %H:%M:%S")
    
    sla_dt = parse_sla_deadline(message.text, base_time=now)
    sla_str = sla_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Add task to SQLite DB
    task_dict = add_task(
        task_text=task_text,
        assignee=assignee,
        author=author,
        sla_deadline=sla_str,
        created_at=created_at_str,
        db_path=DB_PATH
    )

    # Sync to Google Sheets
    if sheets_sync_instance:
        sheets_sync_instance.append_task(task_dict)

async def dispute_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    logger.info(f"=== DISPUTE CALLBACK TRIGGERED: {data} from user @{query.from_user.username} ({query.from_user.id}) ===")

    # Immediately answer the callback query so Telegram stops blinking the button spinner
    try:
        await query.answer("⚖️ Оспаривание начато!\n\nНапишите в этот чат причину несогласия.", show_alert=True)
    except Exception as e:
        logger.error(f"Failed to answer callback query: {e}")

    if data.startswith("dispute_task_"):
        task_id = data.replace("dispute_task_", "")
        user = query.from_user
        username = f"@{user.username}" if user.username else user.first_name

        context.user_data["awaiting_dispute_for_task"] = task_id

        chat_id = query.message.chat_id if query.message else int(TARGET_CHAT_ID)

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚖️ <b>ОСПАРИВАНИЕ ОЦЕНКИ ЗАДАЧИ #{task_id}</b>\n\n"
                     f"👤 <b>{username}</b>, напишите прямо следующим сообщением в этот чат причину вашей оценки / несогласия:\n"
                     f"<i>(Например: Задержка произошла из-за ожидания ответа от курьера...)</i>",
                parse_mode="HTML"
            )
            logger.info(f"Sent dispute prompt for task #{task_id} to chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send dispute prompt message: {e}")


async def dispute_reason_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    awaiting_task_id = context.user_data.get("awaiting_dispute_for_task")
    if not awaiting_task_id:
        return

    reason_text = update.message.text.strip()
    user = update.message.from_user
    username = f"@{user.username}" if user.username else user.first_name

    context.user_data.pop("awaiting_dispute_for_task", None)

    import sqlite3
    dispute_msg = f"Оспаривание от {username}: {reason_text}"
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE tasks SET is_disputed = 1, rating = 0, rating_comment = ? WHERE id = ?", (dispute_msg, awaiting_task_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to update dispute in DB: {e}")

    if sheets_sync_instance:
        try:
            sheets_sync_instance.update_task_dispute(awaiting_task_id, f"{username}: {reason_text}")
        except Exception as e:
            logger.error(f"Failed to sync dispute to Google Sheets: {e}")

    await update.message.reply_text(
        f"✅ <b>АРГУМЕНТ СОХРАНЁН И ОТПРАВЛЕН!</b>\n\n"
        f"Ваше пояснение по задаче #{awaiting_task_id} передано на пересмотр суперверзору:\n"
        f"💬 <i>«{reason_text}»</i>",
        parse_mode="HTML"
    )
