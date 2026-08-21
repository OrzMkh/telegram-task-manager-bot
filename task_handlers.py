import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from task_database import (
    add_task, get_all_tasks, get_user_tasks, get_task, update_task_status, delete_task,
    add_recurring_task, get_all_recurring_tasks, get_recurring_task, delete_recurring_task,
    get_connection
)
from task_sheets_sync import SheetsSyncManager

from task_detector import (
    is_task_message,
    is_recurring_task_message,
    clean_recurring_task_text,
    is_authorized_author,
    extract_assignee,
    extract_author,
    parse_sla_deadline,
    clean_task_text
)
from config import DB_PATH, get_now

logger = logging.getLogger(__name__)

sheets_sync_instance: SheetsSyncManager | None = None
GLOBAL_PENDING_TASKS = {}
GLOBAL_RECURRING_DRAFTS = {}


def set_sheets_sync(manager: SheetsSyncManager):
    global sheets_sync_instance
    sheets_sync_instance = manager


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import ReplyKeyboardMarkup
    help_text = (
        "🤖 <b>Telegram Бот-Менеджер Задач и Отчётов («Байки»)</b>\n\n"
        "<b>📌 Создание задач (руководитель @orzmkh):</b>\n"
        "• Начните сообщение с буквы <b>«З»</b> (например: <code>З @isslamov проверить байки</code>).\n"
        "• Или сделайте Reply на сообщение/голосовое сотрудника с буквой <b>«З»</b>.\n"
        "• Команды: <code>/task &lt;текст&gt;</code> или <code>/задача &lt;текст&gt;</code>.\n\n"
        "<b>📋 Управление и просмотр:</b>\n"
        "• <code>/my</code> или <code>/мои</code> — Показать только ваши актуальные задачи.\n"
        "• <code>/list</code> или <code>/задачи</code> — Список всех активных задач (или <code>/list @username</code>).\n"
        "• <code>/done &lt;ID&gt;</code> — Оценить и завершить задачу."
    )
    keyboard = ReplyKeyboardMarkup(
        [["📋 Мои задачи", "📝 Заполнить отчёт (Байки)"], ["/list", "/reports"]],
        resize_keyboard=True
    )
    await update.message.reply_text(help_text, parse_mode="HTML", reply_markup=keyboard)


GLOBAL_PENDING_TASKS = {}


async def task_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.message.from_user
    if not is_authorized_author(user):
        await update.message.reply_text("⛔ Только руководитель @orzmkh может ставить задачи!", parse_mode="HTML")
        return

    text = update.message.text or update.message.caption or ""
    task_raw_text = clean_task_text(text)

    if not task_raw_text or task_raw_text.lower() in ["/task", "/задача", "/add"]:
        await update.message.reply_text("⚠️ Пожалуйста, укажите текст задачи после команды. Пример: <code>/task Подготовить отчёт</code>", parse_mode="HTML")
        return

    await _process_and_create_task(update, task_raw_text, context=context)


async def my_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.message.from_user
    if not user:
        return

    # If an argument is provided (e.g. /my @isslamov or /мои @isslamov)
    if context.args:
        target_tag = " ".join(context.args).strip()
        display_name = target_tag if target_tag.startswith("@") else f"@{target_tag}"
    else:
        parts = []
        if user.username:
            parts.append(f"@{user.username}")
        if user.first_name:
            parts.append(user.first_name)
        if user.last_name:
            parts.append(user.last_name)
        target_tag = " ".join(parts).strip()
        display_name = f"@{user.username}" if user.username else (user.first_name or f"ID:{user.id}")

    user_tasks = get_user_tasks(target_tag, status="Active", db_path=DB_PATH, sheets_sync=sheets_sync_instance)

    if not user_tasks:
        await update.message.reply_text(
            f"🎉 <b>У вас нет активных задач ({display_name})!</b>\n\n"
            f"Все задачи выполнены или вам пока ничего не назначено.",
            parse_mode="HTML"
        )
        return

    task_blocks = []
    for t in user_tasks:
        t_id = t.get("id")
        t_text = t.get("task_text", "")
        sla = t.get("sla_deadline", "Не указан")
        status_raw = str(t.get("status", "Active"))
        status_label = "⏳ В работе" if status_raw.lower() in ("active", "в работе") else f"⚠️ {status_raw}"
        msg_link = t.get("message_link", "").strip()

        block_lines = [f"🔹 <b>#{t_id}</b>", t_text]
        if msg_link:
            block_lines.append(f"🔗 <a href=\"{msg_link}\">Ссылка на сообщение</a>")
        block_lines.append(f"\n⏰ <b>Дедлайн (SLA):</b> {sla}")
        block_lines.append(f"📊 <b>Статус:</b> {status_label}")

        task_blocks.append("\n".join(block_lines))

    separator = "\n\n──────────────────\n\n"
    body = separator.join(task_blocks)

    assignees = list(dict.fromkeys([t.get("assignee", display_name) for t in user_tasks if t.get("assignee")]))
    authors = list(dict.fromkeys([t.get("author", "@orzmkh") for t in user_tasks if t.get("author")]))
    assignee_str = ", ".join(assignees) if assignees else display_name
    author_str = ", ".join(authors) if authors else "@orzmkh"

    footer = f"\n\n━━━━━━━━━━━━━━━━━━\n👤 <b>Исполнитель:</b> {assignee_str} | ✍️ <b>Автор:</b> {author_str}"
    msg = body + footer

    keyboard_buttons = []
    row = []
    for t in user_tasks:
        t_id = t.get("id")
        row.append(InlineKeyboardButton(f"✅ Выполнил #{t_id}", callback_data=f"complete_task_early_{t_id}"))
        if len(row) == 2:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)
        
    reply_markup = InlineKeyboardMarkup(keyboard_buttons) if keyboard_buttons else None
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)



async def list_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    target_user = context.args[0].strip() if context.args else None
    if target_user:
        active_tasks = get_user_tasks(target_user, status="Active", db_path=DB_PATH, sheets_sync=sheets_sync_instance)
        display_user = target_user if target_user.startswith("@") else f"@{target_user}"
        empty_text = f"📌 На данный момент нет активных задач для {display_user}."
    else:
        active_tasks = get_all_tasks(db_path=DB_PATH, status="Active", sheets_sync=sheets_sync_instance)
        display_user = "Все сотрудники"
        empty_text = "📌 На данный момент нет активных задач."

    if not active_tasks:
        await update.message.reply_text(empty_text, parse_mode="HTML")
        return

    task_blocks = []
    for t in active_tasks:
        t_id = t.get("id")
        t_text = t.get("task_text", "")
        sla = t.get("sla_deadline", "Не указан")
        status_raw = str(t.get("status", "Active"))
        status_label = "⏳ В работе" if status_raw.lower() in ("active", "в работе") else f"⚠️ {status_raw}"
        msg_link = t.get("message_link", "").strip()

        block_lines = [f"🔹 <b>#{t_id}</b>", t_text]
        if msg_link:
            block_lines.append(f"🔗 <a href=\"{msg_link}\">Ссылка на сообщение</a>")
        block_lines.append(f"\n⏰ <b>Дедлайн (SLA):</b> {sla}")
        block_lines.append(f"📊 <b>Статус:</b> {status_label}")

        task_blocks.append("\n".join(block_lines))

    separator = "\n\n──────────────────\n\n"
    body = separator.join(task_blocks)

    assignees = list(dict.fromkeys([t.get("assignee", "") for t in active_tasks if t.get("assignee")]))
    authors = list(dict.fromkeys([t.get("author", "@orzmkh") for t in active_tasks if t.get("author")]))
    assignee_str = ", ".join(assignees) if assignees else display_user
    author_str = ", ".join(authors) if authors else "@orzmkh"

    footer = f"\n\n━━━━━━━━━━━━━━━━━━\n👤 <b>Исполнитель:</b> {assignee_str} | ✍️ <b>Автор:</b> {author_str}"
    msg = body + footer
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)




async def done_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.message.from_user
    if not user:
        return

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

    if is_authorized_author(user):
        # Prompt manager to rate the task 1-5 stars before notifying
        rating_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⭐ 1", callback_data=f"rate_task_{task_id}_1"),
                InlineKeyboardButton("⭐ 2", callback_data=f"rate_task_{task_id}_2"),
                InlineKeyboardButton("⭐ 3", callback_data=f"rate_task_{task_id}_3"),
                InlineKeyboardButton("⭐ 4", callback_data=f"rate_task_{task_id}_4"),
                InlineKeyboardButton("⭐ 5", callback_data=f"rate_task_{task_id}_5"),
            ]
        ])

        await update.message.reply_text(
            f"⭐️ <b>ОЦЕНКА ЗАДАЧИ #{task_id}</b>\n\n"
            f"📋 <b>Задача:</b> {task.get('task_text', '')}\n"
            f"👤 <b>Исполнитель:</b> {task.get('assignee', 'Команда')}\n\n"
            f"Пожалуйста, выберите оценку качества выполнения от 1 до 5:",
            parse_mode="HTML",
            reply_markup=rating_keyboard
        )
    else:
        assignee = task.get("assignee", "")
        username = (user.username or "").lower().replace("@", "").strip()
        
        is_assignee = (
            "команда" in assignee.lower() or 
            username in assignee.lower() or 
            (user.first_name and user.first_name.lower() in assignee.lower())
        )
        
        if not is_assignee:
            await update.message.reply_text(f"⛔ Вы не являетесь исполнителем этой задачи ({assignee})!")
            return

        if task.get("status") in ("Completed", "done"):
            await update.message.reply_text(f"⚠️ Задача #{task_id} уже выполнена.")
            return

        # Mark task as completed (Completed) in SQLite and Sheets
        update_task_status(task_id, "Completed", db_path=DB_PATH)
        if sheets_sync_instance:
            try:
                sheets_sync_instance.update_task_status(task_id, "Completed")
            except Exception as e:
                logger.error(f"Failed to update task #{task_id} status in Sheets: {e}")

        # Send rating prompt to the manager in the chat
        rating_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⭐ 1", callback_data=f"rate_task_{task_id}_1"),
                InlineKeyboardButton("⭐ 2", callback_data=f"rate_task_{task_id}_2"),
                InlineKeyboardButton("⭐ 3", callback_data=f"rate_task_{task_id}_3"),
                InlineKeyboardButton("⭐ 4", callback_data=f"rate_task_{task_id}_4"),
                InlineKeyboardButton("⭐ 5", callback_data=f"rate_task_{task_id}_5"),
            ]
        ])

        await update.message.reply_text(
            f"🔔 <b>ЗАДАЧА #{task_id} ОТМЕЧЕНА КАК ВЫПОЛНЕННАЯ</b>\n\n"
            f"👤 <b>Исполнитель:</b> {assignee} отметил задачу как готовую досрочно.\n"
            f"📋 <b>Задача:</b> {task.get('task_text', '')}\n\n"
            f"👑 <b>@orzmkh, пожалуйста, оцените качество выполнения задачи:</b>",
            parse_mode="HTML",
            reply_markup=rating_keyboard
        )


async def rate_task_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    user = query.from_user
    if not is_authorized_author(user):
        await query.answer("⛔ Только руководитель @orzmkh может оценивать задачи!", show_alert=True)
        return

    if data.startswith("rate_task_"):
        parts = data.split("_")
        task_id = int(parts[2])
        stars = int(parts[3])
        stars_str = "⭐️" * stars

        # Update in DB
        update_task_status(task_id, "Completed", db_path=DB_PATH)
        if sheets_sync_instance:
            sheets_sync_instance.update_task_status(task_id, "Completed")
            sheets_sync_instance.update_task_rating(task_id, stars, is_final=(stars >= 5))

        task = get_task(task_id, db_path=DB_PATH) or {}
        task_text = task.get("task_text", f"Задача #{task_id}")
        assignee = task.get("assignee", "Команда")

        if stars >= 5:
            await query.edit_message_text(
                f"⭐️ <b>ОЦЕНКА ЗАДАЧИ #{task_id}</b>\n\n"
                f"📌 <b>Задача:</b> {task_text}\n"
                f"👤 <b>Исполнитель:</b> {assignee}\n"
                f"👑 <b>Оценка руководителя:</b> {stars_str} (5/5)\n\n"
                f"🎉 <b>Отличная работа!</b> Задача оценена на максимум (5/5) — оспаривание не требуется.",
                parse_mode="HTML"
            )
        else:
            clean_tag = (assignee or "").replace("@", "").strip()
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⚖️ Оспорить оценку", callback_data=f"dispute_task_{task_id}_{clean_tag}")]
            ])
            await query.edit_message_text(
                f"⭐️ <b>ОЦЕНКА ЗАДАЧИ #{task_id}</b>\n\n"
                f"📌 <b>Задача:</b> {task_text}\n"
                f"👤 <b>Исполнитель:</b> {assignee}\n"
                f"👑 <b>Оценка руководителя:</b> {stars_str} ({stars}/5)\n\n"
                f"⚖️ <i>Исполнитель {assignee} может оспорить эту оценку, если не согласен:</i>",
                parse_mode="HTML",
                reply_markup=keyboard
            )


async def message_auto_detector_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text or update.message.caption or ""
    if not text:
        return

    user = update.message.from_user
    if not user:
        return

    # Rule 3: Only @orzmkh can create tasks
    if not is_authorized_author(user):
        return

    text_stripped = text.strip()
    chat = update.message.chat
    logger.info(f"Incoming task message in chat {chat.id} from @{user.username}: '{text_stripped}'")

    # Skip if message starts with other commands (e.g. /start, /help, /list, /done, /report)
    if text_stripped.startswith("/") and not any(text_stripped.startswith(cmd) for cmd in ["/task", "/задача", "/add", "/newtask"]):
        return

    if is_recurring_task_message(text_stripped):
        clean_title = clean_recurring_task_text(text_stripped)
        await _process_and_create_recurring_task(update, clean_title, context=context)
        return

    if is_task_message(text_stripped, user=user):
        task_text = clean_task_text(text_stripped)
        await _process_and_create_task(update, task_text, context=context)



async def _process_and_create_task(update: Update, task_text: str, context: ContextTypes.DEFAULT_TYPE = None, override_assignee: str = ""):
    message = update.message
    if not message:
        return

    assignee = override_assignee or extract_assignee(message)
    author = extract_author(message)

    # Determine message link
    target_msg = message.reply_to_message or message
    target_msg_id = target_msg.message_id
    if message.chat.username:
        msg_link = f"https://t.me/{message.chat.username}/{target_msg_id}"
    else:
        clean_cid = str(message.chat_id).replace("-100", "")
        msg_link = f"https://t.me/c/{clean_cid}/{target_msg_id}"

    # If no @mention in text, do NOT assign replied user. Ask @orzmkh for assignee!
    if not assignee:
        task_draft = {
            "task_text": task_text,
            "author": author,
            "raw_text": message.text or message.caption or task_text,
            "chat_id": message.chat_id,
            "message_id": target_msg_id,
            "message_link": msg_link
        }
        GLOBAL_PENDING_TASKS[str(message.message_id)] = task_draft
        GLOBAL_PENDING_TASKS[str(message.from_user.id)] = task_draft
        if context:
            context.user_data["pending_task"] = task_draft

        assign_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👤 Ильясбек (@isslamov)", callback_data=f"assign_isslamov_{message.message_id}"),
            ],
            [
                InlineKeyboardButton("👤 Мужахид (@axi0603)", callback_data=f"assign_axi0603_{message.message_id}"),
            ],
            [
                InlineKeyboardButton("👤 Жахангир (@Silent_trickster)", callback_data=f"assign_jahangir_{message.message_id}"),
            ],
            [
                InlineKeyboardButton("👥 Вся команда", callback_data=f"assign_team_{message.message_id}"),
            ]
        ])

        sent_msg = await message.reply_text(
            f"⚠️ <b>Укажите исполнителя задачи!</b>\n\n"
            f"📋 <b>Задача:</b> {task_text}\n\n"
            f"Выберите исполнителя из списка ниже или отправьте тег следующим сообщением:",
            parse_mode="HTML",
            reply_markup=assign_keyboard,
            reply_to_message_id=message.message_id
        )
        GLOBAL_PENDING_TASKS[str(sent_msg.message_id)] = task_draft
        return

    task_draft["assignee"] = assignee
    await _prompt_for_sla(update, task_draft, context)



async def delete_task_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    user = query.from_user
    username = (user.username or "").lower().replace("@", "")

    # Security check: ONLY @orzmkh is allowed to delete tasks
    if username != "orzmkh":
        await query.answer("⛔ Только руководитель @orzmkh может удалять задачи!", show_alert=True)
        return

    if data.startswith("delete_task_"):
        task_id_str = data.replace("delete_task_", "")
        if not task_id_str.isdigit():
            await query.answer("⚠️ Неверный ID задачи.", show_alert=True)
            return

        task_id = int(task_id_str)

        # 1. Delete from SQLite DB
        delete_task(task_id, db_path=DB_PATH)

        # 2. Delete from Google Sheets
        if sheets_sync_instance:
            sheets_sync_instance.delete_task(task_id)

        await query.answer(f"🗑 Задача #{task_id} удалена из БД и таблицы!", show_alert=True)

        try:
            await query.edit_message_text(
                f"🗑 <b>Задача #{task_id} удалена из базы и таблицы руководителем @{user.username}.</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Error editing message after task delete: {e}")

async def dispute_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    user = query.from_user
    username = f"@{user.username}" if user.username else user.first_name
    raw_uname = (user.username or "").lower().replace("@", "").strip()

    if data.startswith("dispute_task_"):
        raw_payload = data[len("dispute_task_"):]
        parts = raw_payload.split("_", 1)
        task_id = parts[0]
        cb_assignee = parts[1] if len(parts) > 1 else ""

        clean_num = int(str(task_id).replace("#", "").strip())
        task = get_task(clean_num, db_path=DB_PATH) or {}

        # 1. Determine target assignee from multiple sources
        assignee = task.get("assignee", "") or cb_assignee
        msg_text = (query.message.text or query.message.caption or "") if query.message else ""

        if not assignee and "Исполнитель:" in msg_text:
            try:
                line = [l for l in msg_text.split("\n") if "Исполнитель:" in l][0]
                assignee = line.split("Исполнитель:")[1].strip()
            except Exception:
                pass

        if not assignee and sheets_sync_instance and sheets_sync_instance.sheet:
            try:
                cell = sheets_sync_instance.sheet.find(str(clean_num), in_column=1)
                if cell:
                    row_vals = sheets_sync_instance.sheet.row_values(cell.row)
                    if len(row_vals) > 2:
                        assignee = row_vals[2].strip()
            except Exception:
                pass

        # 2. Strict permission check: ONLY designated assignee(s) can dispute
        if assignee and assignee not in ["Команда", "Сотрудник"]:
            assignee_clean = assignee.lower().replace("@", "")
            allowed_tokens = [tok.strip("@,").lower() for tok in assignee.split() if tok.strip("@,")]

            lead_aliases = {
                "silent_trickster": ["silent_trickster", "silenttrickster", "жахабек", "жахангир", "жахонгир", "жаха", "jaxa", "jakha", "silent"],
                "isslamov": ["isslamov", "isslaamov", "ильясбек", "ильяс", "ilyas"],
                "axi0603": ["axi0603", "мужахидбек", "мужахид", "mujahid", "axi", "orzmkh"]
            }

            is_allowed = (
                (raw_uname and (raw_uname in assignee_clean or assignee_clean in raw_uname or raw_uname in allowed_tokens)) or
                (user.first_name and user.first_name.lower() in assignee_clean) or
                (user.last_name and user.last_name.lower() in assignee_clean) or
                (str(user.id) in assignee)
            )

            # Check lead aliases match
            if not is_allowed:
                for lead_key, aliases in lead_aliases.items():
                    if (raw_uname and raw_uname in aliases) or (user.first_name and any(a in user.first_name.lower() for a in aliases)):
                        if any(a in assignee_clean for a in aliases):
                            is_allowed = True
                            break

            if not is_allowed:
                display_asgn = assignee if assignee.startswith("@") else f"@{assignee}"
                await query.answer(f"⛔ Оспорить оценку может только исполнитель {display_asgn}!", show_alert=True)
                logger.warning(f"Denied dispute attempt by @{user.username} (name={user.first_name}) on task #{clean_num} (assigned to {assignee})")
                return


        # Authorized assignee -> Proceed with dispute
        try:
            await query.answer("⚖️ Оспаривание начато!\n\nНапишите в этот чат причину несогласия.", show_alert=True)
        except Exception as e:
            logger.error(f"Failed to answer callback query: {e}")

        context.user_data["awaiting_dispute_for_task"] = str(clean_num)
        chat_id = query.message.chat_id if query.message else int(TARGET_CHAT_ID)

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚖️ <b>ОСПАРИВАНИЕ ОЦЕНКИ ЗАДАЧИ #{clean_num}</b>\n\n"
                     f"👤 <b>{username}</b>, напишите прямо следующим сообщением в этот чат причину вашей оценки / несогласия:\n"
                     f"<i>(Например: Задержка произошла из-за ожидания ответа от курьера...)</i>",
                parse_mode="HTML"
            )
            logger.info(f"Sent dispute prompt for task #{clean_num} to chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send dispute prompt message: {e}")


async def assign_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    user = query.from_user
    if not is_authorized_author(user):
        await query.answer("⛔ Только руководитель может назначать исполнителя!", show_alert=True)
        return

    parts = data.split("_")
    action_key = f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else data
    msg_id = parts[2] if len(parts) >= 3 else ""

    assignee_map = {
        "assign_isslamov": "@isslamov",
        "assign_axi0603": "@axi0603",
        "assign_orzmkh": "@orzmkh",
        "assign_jahangir": "@Silent_trickster",
        "assign_team": "Команда",
    }
    assignee = assignee_map.get(action_key, "Команда")

    # Look up pending task draft from multiple persistent locations
    pending = None
    if msg_id and str(msg_id) in GLOBAL_PENDING_TASKS:
        pending = GLOBAL_PENDING_TASKS.pop(str(msg_id))
    elif query.message and str(query.message.message_id) in GLOBAL_PENDING_TASKS:
        pending = GLOBAL_PENDING_TASKS.pop(str(query.message.message_id))
    elif str(user.id) in GLOBAL_PENDING_TASKS:
        pending = GLOBAL_PENDING_TASKS.pop(str(user.id))
    elif context and "pending_task" in context.user_data:
        pending = context.user_data.pop("pending_task")

    # Fallback to extracting task text from prompt message if memory was purged
    if not pending and query.message:
        msg_body = query.message.text or query.message.caption or ""
        if "Задача:" in msg_body:
            try:
                line = [l for l in msg_body.split("\n") if "Задача:" in l][0]
                extracted_txt = line.split("Задача:")[1].strip()
                if extracted_txt:
                    pending = {
                        "task_text": extracted_txt,
                        "author": f"@{user.username}" if user.username else "@orzmkh",
                        "raw_text": extracted_txt
                    }
            except Exception:
                pass

    if not pending:
        await query.answer("⚠️ Задача уже зафиксирована.", show_alert=True)
        return

    await query.answer(f"Исполнитель: {assignee}")
    pending["assignee"] = assignee
    GLOBAL_PENDING_TASKS[str(query.message.message_id)] = pending
    await _prompt_for_sla(update, pending, context)



async def dispute_reason_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user = update.message.from_user
    user_id_str = str(user.id) if user else ""

    # Check if awaiting custom SLA text
    awaiting_sla_msg_id = context.user_data.get("awaiting_sla_for_msg_id") if context else None
    if awaiting_sla_msg_id and is_authorized_author(user):
        if context:
            context.user_data.pop("awaiting_sla_for_msg_id", None)
        pending = GLOBAL_PENDING_TASKS.pop(str(awaiting_sla_msg_id), None)
        if pending:
            sla_text = update.message.text.strip()
            now = get_now()
            sla_dt = parse_sla_deadline(sla_text, base_time=now)
            sla_str = sla_dt.strftime("%Y-%m-%d %H:%M:%S")
            await _finalize_task_creation(
                update=update,
                context=context,
                pending=pending,
                sla_str=sla_str,
                reply_to_msg_id=update.message.message_id
            )
            return

    # 1. Check if there is a pending task waiting for @orzmkh to specify assignee
    pending = None
    if context and "pending_task" in context.user_data:
        pending = context.user_data.pop("pending_task")
    elif user_id_str and user_id_str in GLOBAL_PENDING_TASKS:
        pending = GLOBAL_PENDING_TASKS.pop(user_id_str)

    if pending and is_authorized_author(user):
        text_in = update.message.text.strip()
        mentions = re.findall(r"@[\w_]+", text_in)
        assignee = " ".join(mentions) if mentions else (text_in if text_in.startswith("@") else f"@{text_in}")

        pending["assignee"] = assignee
        await _prompt_for_sla(update, pending, context)
        return

    # 2. Check if awaiting dispute reason
    awaiting_task_id = context.user_data.get("awaiting_dispute_for_task")
    if not awaiting_task_id:
        return

    reason_text = update.message.text.strip()
    user = update.message.from_user
    username = f"@{user.username}" if user.username else user.first_name

    context.user_data.pop("awaiting_dispute_for_task", None)

    clean_task_num = int(str(awaiting_task_id).replace("#", "").strip())
    dispute_msg = f"Оспаривание от {username}: {reason_text}"
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE tasks SET is_disputed = 1, status = 'Disputed', rating = 0, rating_comment = ? WHERE id = ?", (dispute_msg, clean_task_num))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to update dispute in DB: {e}")

    if sheets_sync_instance:
        try:
            sheets_sync_instance.update_task_dispute(clean_task_num, f"{username}: {reason_text}")
        except Exception as e:
            logger.error(f"Failed to sync dispute to Google Sheets: {e}")

    await update.message.reply_text(
        f"✅ <b>АРГУМЕНТ СОХРАНЁН И ОТПРАВЛЕН!</b>\n\n"
        f"Ваше пояснение по задаче #{awaiting_task_id} передано на пересмотр суперверзору:\n"
        f"💬 <i>«{reason_text}»</i>",
        parse_mode="HTML"
    )


# ==========================================
# RECURRING TASKS (ПОСТОЯННЫЕ ЗАДАЧИ - ЗП/ZP)
# ==========================================

async def _process_and_create_recurring_task(update: Update, title: str, context: ContextTypes.DEFAULT_TYPE = None):
    message = update.message
    if not message:
        return

    author = extract_author(message)
    assignee = extract_assignee(message)
    draft_id = str(message.message_id)

    target_msg = message.reply_to_message or message
    target_msg_id = target_msg.message_id
    if message.chat.username:
        msg_link = f"https://t.me/{message.chat.username}/{target_msg_id}"
    else:
        clean_cid = str(message.chat_id).replace("-100", "").replace("-", "")
        msg_link = f"https://t.me/c/{clean_cid}/{target_msg_id}"

    draft = {
        "title": title,
        "author": author,
        "assignee": assignee,
        "frequency": "",
        "day_of_week": "",
        "message_link": msg_link,
        "chat_id": message.chat_id,
        "message_id": target_msg_id
    }
    GLOBAL_RECURRING_DRAFTS[draft_id] = draft

    # Step 1: If assignee not known, prompt for assignee
    if not assignee:
        assign_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Ильясбек (@isslamov)", callback_data=f"recasgn_isslamov_{draft_id}")],
            [InlineKeyboardButton("👤 Мужахид (@axi0603)", callback_data=f"recasgn_axi0603_{draft_id}")],
            [InlineKeyboardButton("👤 Жахангир (@Silent_trickster)", callback_data=f"recasgn_jahangir_{draft_id}")],
            [InlineKeyboardButton("👥 Вся команда", callback_data=f"recasgn_team_{draft_id}")],
        ])
        sent_msg = await message.reply_text(
            f"🔄 <b>ПОСТОЯННАЯ ЗАДАЧА (Шаг 1 из 3)</b>\n\n"
            f"📋 <b>Задача:</b> {title}\n\n"
            f"👤 <b>Выберите исполнителя:</b>",
            parse_mode="HTML",
            reply_markup=assign_keyboard,
            reply_to_message_id=message.message_id
        )
        GLOBAL_RECURRING_DRAFTS[str(sent_msg.message_id)] = draft
        return

    # If assignee was specified in text via @mention, go straight to Step 2 (Frequency)
    await _send_recurring_frequency_step(message, draft, draft_id, is_edit=False)


async def _send_recurring_frequency_step(message_or_query, draft: dict, draft_id: str, is_edit: bool = False):
    freq_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Раз в неделю", callback_data=f"recfreq_weekly_{draft_id}")],
        [InlineKeyboardButton("🗓 Раз в 2 недели", callback_data=f"recfreq_biweekly_{draft_id}")],
        [InlineKeyboardButton("📆 Раз в месяц", callback_data=f"recfreq_monthly_{draft_id}")],
        [InlineKeyboardButton("⚡️ Каждый рабочий день", callback_data=f"recfreq_daily_{draft_id}")],
    ])
    text = (
        f"🔄 <b>ПОСТОЯННАЯ ЗАДАЧА (Шаг 2 из 3)</b>\n\n"
        f"📋 <b>Задача:</b> {draft['title']}\n"
        f"👤 <b>Исполнитель:</b> {draft['assignee']}\n\n"
        f"🔄 <b>Как часто необходимо выполнять задачу?</b>"
    )
    if is_edit:
        await message_or_query.edit_message_text(text, parse_mode="HTML", reply_markup=freq_keyboard)
    else:
        sent_msg = await message_or_query.reply_text(text, parse_mode="HTML", reply_markup=freq_keyboard, reply_to_message_id=draft.get("message_id"))
        GLOBAL_RECURRING_DRAFTS[str(sent_msg.message_id)] = draft


async def _send_recurring_day_step(query, draft: dict, draft_id: str):
    freq_labels = {
        "weekly": "Раз в неделю",
        "biweekly": "Раз в 2 недели",
        "monthly": "Раз в месяц",
        "daily": "Каждый рабочий день"
    }
    freq_text = freq_labels.get(draft.get("frequency"), "Периодически")

    if draft.get("frequency") == "daily":
        draft["day_of_week"] = "Пн-Пт"
        await _finish_recurring_task_creation(query, draft, draft_id)
        return

    days_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Пн (Понедельник)", callback_data=f"recday_Пн_{draft_id}"),
            InlineKeyboardButton("Вт (Вторник)", callback_data=f"recday_Вт_{draft_id}"),
        ],
        [
            InlineKeyboardButton("Ср (Среда)", callback_data=f"recday_Ср_{draft_id}"),
            InlineKeyboardButton("Чт (Четверг)", callback_data=f"recday_Чт_{draft_id}"),
        ],
        [
            InlineKeyboardButton("Пт (Пятница)", callback_data=f"recday_Пт_{draft_id}"),
            InlineKeyboardButton("Сб (Суббота)", callback_data=f"recday_Сб_{draft_id}"),
        ],
        [
            InlineKeyboardButton("Вс (Воскресенье)", callback_data=f"recday_Вс_{draft_id}"),
        ]
    ])

    text = (
        f"🔄 <b>ПОСТОЯННАЯ ЗАДАЧА (Шаг 3 из 3)</b>\n\n"
        f"📋 <b>Задача:</b> {draft['title']}\n"
        f"👤 <b>Исполнитель:</b> {draft['assignee']}\n"
        f"🔄 <b>Частота:</b> {freq_text}\n\n"
        f"📅 <b>В какой день недели выполнять задачу?</b>"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=days_keyboard)


async def _finish_recurring_task_creation(query, draft: dict, draft_id: str):
    from config import get_now
    created_at_str = get_now().strftime("%Y-%m-%d %H:%M:%S")

    freq_labels = {
        "weekly": "Раз в неделю",
        "biweekly": "Раз в 2 недели",
        "monthly": "Раз в месяц",
        "daily": "Каждый рабочий день"
    }
    freq_text = freq_labels.get(draft.get("frequency"), draft.get("frequency", "Периодически"))
    day_str = draft.get("day_of_week", "Пн")

    # Save to SQLite DB
    task_dict = add_recurring_task(
        title=draft["title"],
        assignee=draft["assignee"],
        author=draft["author"],
        frequency=freq_text,
        day_of_week=day_str,
        created_at=created_at_str,
        message_link=draft.get("message_link", ""),
        db_path=DB_PATH
    )

    task_id = task_dict.get("id")

    # Sync to Google Sheets
    if sheets_sync_instance and hasattr(sheets_sync_instance, "append_recurring_task"):
        try:
            sheets_sync_instance.append_recurring_task(task_dict)
        except Exception as e:
            logger.error(f"Error syncing recurring task #{task_id} to Google Sheets: {e}")

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Удалить задачу", callback_data=f"delrec_{task_id}")]
    ])

    link_str = f"\n🔗 <a href='{draft['message_link']}'>Ссылка на исходное сообщение</a>" if draft.get("message_link") else ""

    confirm_text = (
        f"✅ <b>ПОСТОЯННАЯ ЗАДАЧА #{task_id} СОЗДАНА</b>\n\n"
        f"📋 <b>Задача:</b> {draft['title']}\n"
        f"👤 <b>Исполнитель:</b> {draft['assignee']}\n"
        f"✍️ <b>Постановщик:</b> {draft['author']}\n"
        f"🔄 <b>Периодичность:</b> {freq_text}\n"
        f"📅 <b>День выполнения:</b> {day_str}{link_str}\n"
        f"📊 <b>Статус:</b> Занесена в систему и открыта для оценки в Web App\n\n"
        f"🌐 <i>Оценивать выполнение этой задачи можно в дашборде в разделе «Постоянные задачи»</i>"
    )

    await query.edit_message_text(confirm_text, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)


async def recurring_task_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    user = query.from_user

    # Delete recurring task handler
    if data.startswith("delrec_"):
        if not is_authorized_author(user):
            await query.answer("⛔ Только руководитель может удалять задачи!", show_alert=True)
            return
        rec_id_str = data.replace("delrec_", "").strip()
        try:
            clean_rec_id = int(rec_id_str)
            delete_recurring_task(clean_rec_id, db_path=DB_PATH)
            await query.answer(f"Постоянная задача #{clean_rec_id} удалена.")
            await query.edit_message_text(f"🗑 <b>Постоянная задача #{clean_rec_id} удалена из системы.</b>", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error deleting recurring task: {e}")
            await query.answer("Ошибка при удалении задачи.", show_alert=True)
        return

    if not is_authorized_author(user):
        await query.answer("⛔ Только руководитель может настраивать постоянные задачи!", show_alert=True)
        return

    parts = data.split("_")
    prefix = parts[0]
    val = parts[1] if len(parts) >= 2 else ""
    draft_id = parts[2] if len(parts) >= 3 else ""

    # Find draft
    draft = GLOBAL_RECURRING_DRAFTS.get(draft_id) or (GLOBAL_RECURRING_DRAFTS.get(str(query.message.message_id)) if query.message else None)

    if not draft and query.message:
        # Fallback extract title
        msg_txt = query.message.text or ""
        if "Задача:" in msg_txt:
            try:
                line = [l for l in msg_txt.split("\n") if "Задача:" in l][0]
                t_val = line.split("Задача:")[1].strip()
                draft = {
                    "title": t_val,
                    "author": f"@{user.username}" if user.username else "@orzmkh",
                    "assignee": "",
                    "frequency": "",
                    "day_of_week": "",
                    "message_link": ""
                }
            except Exception:
                pass

    if not draft:
        await query.answer("⚠️ Сессия настройки истекла. Поставьте задачу снова через 'ЗП'.", show_alert=True)
        return

    # 1. Step 1 -> Assignee chosen
    if prefix == "recasgn":
        assignee_map = {
            "isslamov": "@isslamov",
            "axi0603": "@axi0603",
            "jahangir": "@Silent_trickster",
            "team": "Команда",
        }
        draft["assignee"] = assignee_map.get(val, "Команда")
        await query.answer(f"Исполнитель: {draft['assignee']}")
        await _send_recurring_frequency_step(query, draft, draft_id, is_edit=True)

    # 2. Step 2 -> Frequency chosen
    elif prefix == "recfreq":
        draft["frequency"] = val
        await query.answer(f"Частота: {val}")
        await _send_recurring_day_step(query, draft, draft_id)

    # 3. Step 3 -> Day of week chosen
    elif prefix == "recday":
        draft["day_of_week"] = val
        await query.answer(f"День: {val}")
        await _finish_recurring_task_creation(query, draft, draft_id)


# --- SLA & INTERACTIVE CALENDAR SELECTION FUNCTIONS ---

def get_sla_keyboard(msg_id: str) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("⚡ 1 час", callback_data=f"sla_preset_1h_{msg_id}"),
            InlineKeyboardButton("⚡ 3 часа", callback_data=f"sla_preset_3h_{msg_id}")
        ],
        [
            InlineKeyboardButton("🌇 До конца дня (18:00)", callback_data=f"sla_preset_today18_{msg_id}"),
            InlineKeyboardButton("📅 Завтра (18:00)", callback_data=f"sla_preset_tomorrow18_{msg_id}")
        ],
        [
            InlineKeyboardButton("📅 Выбрать дату (Календарь)", callback_data=f"sla_cal_init_{msg_id}")
        ],
        [
            InlineKeyboardButton("⌨️ Указать вручную", callback_data=f"sla_preset_custom_{msg_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def generate_calendar_keyboard(year: int, month: int, msg_id: str) -> InlineKeyboardMarkup:
    import calendar
    keyboard = []
    
    # Header: Month and Year
    months_names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
        7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    month_name = months_names.get(month, f"Месяц {month}")
    keyboard.append([
        InlineKeyboardButton(f"{month_name} {year}", callback_data=f"cal_ignore_{msg_id}")
    ])
    
    # Weekdays Header
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([
        InlineKeyboardButton(w, callback_data=f"cal_ignore_{msg_id}") for w in weekdays
    ])
    
    # Calendar month days
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data=f"cal_ignore_{msg_id}"))
            else:
                row.append(InlineKeyboardButton(str(day), callback_data=f"cal_day_{year}_{month}_{day}_{msg_id}"))
        keyboard.append(row)
        
    # Navigation Row
    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
        
    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year += 1
        
    keyboard.append([
        InlineKeyboardButton("◀️", callback_data=f"cal_nav_{prev_year}_{prev_month}_{msg_id}"),
        InlineKeyboardButton("Назад", callback_data=f"sla_back_{msg_id}"),
        InlineKeyboardButton("▶️", callback_data=f"cal_nav_{next_year}_{next_month}_{msg_id}")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def generate_time_keyboard(year: int, month: int, day: int, msg_id: str) -> InlineKeyboardMarkup:
    times = [
        ["08:00", "10:00", "12:00", "14:00"],
        ["16:00", "18:00", "20:00", "22:00"]
    ]
    keyboard = []
    for row in times:
        keyboard_row = []
        for t in row:
            hh, mm = t.split(":")
            keyboard_row.append(
                InlineKeyboardButton(t, callback_data=f"cal_time_{year}_{month}_{day}_{hh}_{mm}_{msg_id}")
            )
        keyboard.append(keyboard_row)
        
    keyboard.append([
        InlineKeyboardButton("◀️ Назад к календарю", callback_data=f"cal_nav_{year}_{month}_{msg_id}")
    ])
    return InlineKeyboardMarkup(keyboard)


async def _prompt_for_sla(update: Update, task_draft: dict, context: ContextTypes.DEFAULT_TYPE):
    sla_keyboard = get_sla_keyboard(str(task_draft["message_id"]))
    confirm_text = (
        f"⏰ <b>Укажите срок выполнения (SLA)!</b>\n\n"
        f"📋 <b>Задача:</b> {task_draft['task_text']}\n"
        f"👤 <b>Исполнитель:</b> {task_draft['assignee']}\n\n"
        f"Выберите быстрый срок или нажмите кнопку для выбора даты на календаре:"
    )
    
    query = update.callback_query
    if query:
        sent_msg = query.message
        await query.edit_message_text(
            confirm_text,
            parse_mode="HTML",
            reply_markup=sla_keyboard
        )
        GLOBAL_PENDING_TASKS[str(sent_msg.message_id)] = task_draft
    else:
        message = update.message
        sent_msg = await message.reply_text(
            confirm_text,
            parse_mode="HTML",
            reply_markup=sla_keyboard,
            reply_to_message_id=message.message_id
        )
        GLOBAL_PENDING_TASKS[str(sent_msg.message_id)] = task_draft


async def _finalize_task_creation(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict, sla_str: str, reply_to_msg_id: int = None, query = None):
    task_text = pending.get("task_text", "")
    assignee = pending.get("assignee", "Команда")
    author = pending.get("author", "@orzmkh")
    
    now = get_now()
    created_at_str = now.strftime("%Y-%m-%d %H:%M:%S")
    
    task_dict = add_task(
        task_text=task_text,
        assignee=assignee,
        author=author,
        sla_deadline=sla_str,
        created_at=created_at_str,
        message_link=pending.get("message_link", ""),
        db_path=DB_PATH
    )

    canonical_id = task_dict.get("id")

    if sheets_sync_instance:
        try:
            sheet_id = sheets_sync_instance.append_task(task_dict)
            if sheet_id:
                canonical_id = sheet_id
                task_dict["id"] = canonical_id
                try:
                    with get_connection(DB_PATH) as conn:
                        conn.cursor().execute("UPDATE tasks SET id = ? WHERE rowid = (SELECT max(rowid) FROM tasks)", (canonical_id,))
                        conn.commit()
                except Exception as db_e:
                    logger.error(f"Failed to update task ID in DB: {db_e}")
            logger.info(f"Task #{canonical_id} synced to Google Sheets.")
        except Exception as e:
            logger.error(f"Error syncing task #{canonical_id} to Google Sheets: {e}")

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Удалить задачу", callback_data=f"delete_task_{canonical_id}")]
    ])

    confirm_text = (
        f"✅ <b>ЗАДАЧА #{canonical_id} ЗАФИКСИРОВАНА</b>\n\n"
        f"📋 <b>Задача:</b> {task_text}\n"
        f"👤 <b>Исполнитель:</b> {assignee}\n"
        f"✍️ <b>Постановщик:</b> {author}\n"
        f"⏰ <b>Дедлайн SLA:</b> {sla_str}\n"
        f"📊 <b>Статус:</b> Занесена в БД и Google Таблицу"
    )

    if query:
        try:
            await query.edit_message_text(
                confirm_text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
    else:
        chat_id = update.message.chat_id if update.message else pending.get("chat_id")
        await context.bot.send_message(
            chat_id=chat_id,
            text=confirm_text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            reply_to_message_id=reply_to_msg_id
        )

    if assignee and assignee != "Команда":
        try:
            chat_id = query.message.chat_id if query and query.message else (update.message.chat_id if update.message else pending.get("chat_id"))
            
            # Inline button for the employee to complete early
            complete_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Выполнил(а) задачу", callback_data=f"complete_task_early_{canonical_id}")]
            ])
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎯 {assignee}, вам назначена задача <b>#{canonical_id}</b>: <i>{task_text}</i>\n⏰ Срок / SLA: <b>{sla_str}</b>",
                parse_mode="HTML",
                reply_markup=complete_keyboard
            )
        except Exception as e_tag:
            logger.warning(f"Could not send tag message to assignee: {e_tag}")


async def sla_preset_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    user = query.from_user
    if not is_authorized_author(user):
        await query.answer("⛔ Только руководитель может задавать SLA!", show_alert=True)
        return

    parts = data.split("_")
    preset_type = parts[2]
    msg_id = parts[3] if len(parts) > 3 else ""

    pending = GLOBAL_PENDING_TASKS.pop(str(query.message.message_id), None)
    if not pending and msg_id:
        pending = GLOBAL_PENDING_TASKS.pop(str(msg_id), None)

    if not pending:
        await query.answer("⚠️ Черновик задачи не найден или уже сохранён.", show_alert=True)
        return

    now = get_now()
    if preset_type == "1h":
        sla_dt = now + timedelta(hours=1)
    elif preset_type == "3h":
        sla_dt = now + timedelta(hours=3)
    elif preset_type == "today18":
        sla_dt = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now >= sla_dt:
            sla_dt += timedelta(days=1)
    elif preset_type == "tomorrow18":
        sla_dt = (now + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    elif preset_type == "custom":
        context.user_data["awaiting_sla_for_msg_id"] = str(query.message.message_id)
        GLOBAL_PENDING_TASKS[str(query.message.message_id)] = pending
        await query.edit_message_text(
            f"✍️ <b>Укажите срок вручную сообщением в этот чат.</b>\n\n"
            f"📋 <b>Задача:</b> {pending['task_text']}\n"
            f"👤 <b>Исполнитель:</b> {pending['assignee']}\n\n"
            f"Примеры ввода:\n"
            f"• `25.08 14:00` (25 августа в 14:00)\n"
            f"• `завтра 18:00`\n"
            f"• `через 2 часа`",
            parse_mode="HTML"
        )
        await query.answer()
        return
    else:
        sla_dt = now + timedelta(days=1)

    sla_str = sla_dt.strftime("%Y-%m-%d %H:%M:%S")
    await query.answer(f"SLA установлен: {sla_str}")
    
    await _finalize_task_creation(
        update=update,
        context=context,
        pending=pending,
        sla_str=sla_str,
        query=query
    )


async def sla_cal_init_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    user = query.from_user
    if not is_authorized_author(user):
        await query.answer("⛔ Только руководитель может использовать календарь!", show_alert=True)
        return

    parts = data.split("_")
    msg_id = parts[3] if len(parts) >= 4 else ""

    pending = GLOBAL_PENDING_TASKS.get(str(query.message.message_id))
    if not pending and msg_id:
        pending = GLOBAL_PENDING_TASKS.get(str(msg_id))

    if not pending:
        await query.answer("⚠️ Черновик задачи не найден.", show_alert=True)
        return

    now = get_now()
    reply_markup = generate_calendar_keyboard(now.year, now.month, msg_id or str(query.message.message_id))
    
    await query.edit_message_text(
        f"📅 <b>Выберите дату окончания SLA:</b>\n\n"
        f"📋 <b>Задача:</b> {pending['task_text']}\n"
        f"👤 <b>Исполнитель:</b> {pending['assignee']}\n",
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    await query.answer()


async def cal_nav_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    parts = data.split("_")
    if len(parts) < 5:
        await query.answer("⚠️ Ошибка навигации.", show_alert=True)
        return

    year = int(parts[2])
    month = int(parts[3])
    msg_id = parts[4]

    pending = GLOBAL_PENDING_TASKS.get(str(query.message.message_id))
    if not pending and msg_id:
        pending = GLOBAL_PENDING_TASKS.get(str(msg_id))

    if not pending:
        await query.answer("⚠️ Черновик задачи не найден.", show_alert=True)
        return

    reply_markup = generate_calendar_keyboard(year, month, msg_id)
    await query.edit_message_text(
        f"📅 <b>Выберите дату окончания SLA:</b>\n\n"
        f"📋 <b>Задача:</b> {pending['task_text']}\n"
        f"👤 <b>Исполнитель:</b> {pending['assignee']}\n",
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    await query.answer()


async def cal_day_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    parts = data.split("_")
    if len(parts) < 6:
        await query.answer("⚠️ Ошибка выбора дня.", show_alert=True)
        return

    year = int(parts[2])
    month = int(parts[3])
    day = int(parts[4])
    msg_id = parts[5]

    pending = GLOBAL_PENDING_TASKS.get(str(query.message.message_id))
    if not pending and msg_id:
        pending = GLOBAL_PENDING_TASKS.get(str(msg_id))

    if not pending:
        await query.answer("⚠️ Черновик задачи не найден.", show_alert=True)
        return

    reply_markup = generate_time_keyboard(year, month, day, msg_id)
    await query.edit_message_text(
        f"⏰ <b>Выберите время окончания SLA ({day:02d}.{month:02d}.{year}):</b>\n\n"
        f"📋 <b>Задача:</b> {pending['task_text']}\n"
        f"👤 <b>Исполнитель:</b> {pending['assignee']}\n",
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    await query.answer()


async def cal_time_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    parts = data.split("_")
    if len(parts) < 8:
        await query.answer("⚠️ Ошибка выбора времени.", show_alert=True)
        return

    year = int(parts[2])
    month = int(parts[3])
    day = int(parts[4])
    hh = int(parts[5])
    mm = int(parts[6])
    msg_id = parts[7]

    pending = GLOBAL_PENDING_TASKS.pop(str(query.message.message_id), None)
    if not pending and msg_id:
        pending = GLOBAL_PENDING_TASKS.pop(str(msg_id), None)

    if not pending:
        await query.answer("⚠️ Черновик задачи не найден или уже сохранён.", show_alert=True)
        return

    sla_dt = datetime(year, month, day, hh, mm, 0)
    sla_str = sla_dt.strftime("%Y-%m-%d %H:%M:%S")

    await query.answer(f"SLA установлен: {sla_str}")
    
    await _finalize_task_creation(
        update=update,
        context=context,
        pending=pending,
        sla_str=sla_str,
        query=query
    )


async def cal_ignore_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()


async def sla_back_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    parts = data.split("_")
    msg_id = parts[2] if len(parts) >= 3 else ""

    pending = GLOBAL_PENDING_TASKS.get(str(query.message.message_id))
    if not pending and msg_id:
        pending = GLOBAL_PENDING_TASKS.get(str(msg_id))

    if not pending:
        await query.answer("⚠️ Черновик задачи не найден.", show_alert=True)
        return

    sla_keyboard = get_sla_keyboard(msg_id or str(query.message.message_id))
    await query.edit_message_text(
        f"⏰ <b>Укажите срок выполнения (SLA)!</b>\n\n"
        f"📋 <b>Задача:</b> {pending['task_text']}\n"
        f"👤 <b>Исполнитель:</b> {pending['assignee']}\n\n"
        f"Выберите быстрый срок или нажмите кнопку для выбора даты на календаре:",
        parse_mode="HTML",
        reply_markup=sla_keyboard
    )
    await query.answer()


async def complete_task_early_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    user = query.from_user
    username = (user.username or "").lower().replace("@", "").strip()

    if data.startswith("complete_task_early_"):
        task_id_str = data.replace("complete_task_early_", "")
        if not task_id_str.isdigit():
            await query.answer("⚠️ Неверный ID задачи.", show_alert=True)
            return

        task_id = int(task_id_str)
        task = get_task(task_id, db_path=DB_PATH)

        if not task:
            await query.answer(f"❌ Задача #{task_id} не найдена.", show_alert=True)
            return

        assignee = task.get("assignee", "")
        # Is the employee authorized to complete this task?
        is_assignee = (
            "команда" in assignee.lower() or 
            username in assignee.lower() or 
            (user.first_name and user.first_name.lower() in assignee.lower()) or
            is_authorized_author(user)  # Manager can also complete
        )

        if not is_assignee:
            await query.answer(f"⛔ Вы не являетесь исполнителем этой задачи ({assignee})!", show_alert=True)
            return

        # Check if already completed
        if task.get("status") in ("Completed", "done"):
            await query.answer("⚠️ Задача уже выполнена.", show_alert=True)
            return

        # Mark task as completed (Completed) in SQLite and Sheets
        update_task_status(task_id, "Completed", db_path=DB_PATH)
        if sheets_sync_instance:
            try:
                sheets_sync_instance.update_task_status(task_id, "Completed")
            except Exception as e:
                logger.error(f"Failed to update task #{task_id} status in Sheets: {e}")

        await query.answer("✅ Задача отмечена как выполненная!")

        # Edit original message to remove button or update text
        try:
            msg_text = query.message.text or query.message.caption or ""
            if f"#{task_id}" in msg_text:
                if "Мои задачи" in msg_text or "Мои активные задачи" in msg_text or "Список активных задач" in msg_text:
                    # Regenerate /my list buttons
                    target_tag = f"@{user.username}" if user.username else user.first_name
                    user_tasks = get_user_tasks(target_tag, status="Active", db_path=DB_PATH, sheets_sync=sheets_sync_instance)
                    keyboard_buttons = []
                    row = []
                    for t in user_tasks:
                        t_id = t.get("id")
                        row.append(InlineKeyboardButton(f"✅ Выполнил #{t_id}", callback_data=f"complete_task_early_{t_id}"))
                        if len(row) == 2:
                            keyboard_buttons.append(row)
                            row = []
                    if row:
                        keyboard_buttons.append(row)
                    reply_markup = InlineKeyboardMarkup(keyboard_buttons) if keyboard_buttons else None
                    await query.edit_message_reply_markup(reply_markup=reply_markup)
                else:
                    # Single tag message
                    await query.edit_message_text(
                        f"🎯 {assignee}, вам назначена задача <b>#{task_id}</b>: <i>{task.get('task_text', '')}</i>\n"
                        f"⏰ Срок / SLA: <b>{task.get('sla_deadline', '')}</b>\n\n"
                        f"✅ <i>Отмечена как выполненная исполнителем @{user.username or user.first_name}.</i>",
                        parse_mode="HTML"
                    )
            else:
                await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e_edit:
            logger.error(f"Failed to edit message after early completion: {e_edit}")

        # Send rating prompt to the manager in the chat
        rating_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⭐ 1", callback_data=f"rate_task_{task_id}_1"),
                InlineKeyboardButton("⭐ 2", callback_data=f"rate_task_{task_id}_2"),
                InlineKeyboardButton("⭐ 3", callback_data=f"rate_task_{task_id}_3"),
                InlineKeyboardButton("⭐ 4", callback_data=f"rate_task_{task_id}_4"),
                InlineKeyboardButton("⭐ 5", callback_data=f"rate_task_{task_id}_5"),
            ]
        ])

        chat_id = query.message.chat_id if query.message else int(TASK_CHAT_ID)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔔 <b>ЗАДАЧА #{task_id} ОТМЕЧЕНА КАК ВЫПОЛНЕННАЯ</b>\n\n"
                 f"👤 <b>Исполнитель:</b> {assignee} отметил задачу как готовую досрочно.\n"
                 f"📋 <b>Задача:</b> {task.get('task_text', '')}\n\n"
                 f"👑 <b>@orzmkh, пожалуйста, оцените качество выполнения задачи:</b>",
            parse_mode="HTML",
            reply_markup=rating_keyboard
        )


