import datetime
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from task_database import add_bike_report, get_bike_reports
from config import DB_PATH

logger = logging.getLogger(__name__)


# Conversation states
(
    REPORT_DATE,
    ISSUED,
    RETURNED,
    TOTAL_IN_TRIP,
    NEW_BIKES,
    OLD_BIKES,
    BROKEN_BIKES,
    REASONS,
    COMMENT,
    CONFIRM,
) = range(10)

CANCEL_TEXT = "❌ Отмена"
SKIP_TEXT = "⏩ Пропустить"
CONFIRM_TEXT = "✅ Отправить"
RESTART_TEXT = "✏️ Заполнить заново"

def get_today_str() -> str:
    return datetime.datetime.now().strftime("%d.%m.%Y")

async def start_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["report"] = {}
    today = get_today_str()
    reply_keyboard = [[f"📅 Сегодня ({today})"], [CANCEL_TEXT]]
    
    text = (
        "📝 **Заполнение отчёта «Байки»**\n\n"
        "Шаг 1 из 9: **Укажите дату отчёта** (например: `31.07.2026` или нажмите кнопку ниже):"
    )
    
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True, one_time_keyboard=True),
    )
    return REPORT_DATE

async def date_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    input_text = update.message.text.strip()
    if input_text == CANCEL_TEXT:
        return await cancel_report(update, context)
    
    if "📅 Сегодня" in input_text:
        report_date = get_today_str()
    else:
        report_date = input_text

    context.user_data["report"]["report_date"] = report_date

    reply_keyboard = [[CANCEL_TEXT]]
    await update.message.reply_text(
        f"✅ Дата: **{report_date}**\n\n"
        "Шаг 2 из 9: **Укажите количество выданных байков («Выдано»)**:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    return ISSUED

async def issued_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == CANCEL_TEXT:
        return await cancel_report(update, context)

    context.user_data["report"]["issued"] = text
    reply_keyboard = [[CANCEL_TEXT]]
    await update.message.reply_text(
        "Шаг 3 из 9: **Укажите количество вернувшихся байков («Вернули»)**:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    return RETURNED

async def returned_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == CANCEL_TEXT:
        return await cancel_report(update, context)

    context.user_data["report"]["returned"] = text
    reply_keyboard = [[CANCEL_TEXT]]
    await update.message.reply_text(
        "Шаг 4 из 9: **Укажите общее количество байков в поездке («Всего в поездке»)**:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    return TOTAL_IN_TRIP

async def total_in_trip_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == CANCEL_TEXT:
        return await cancel_report(update, context)

    context.user_data["report"]["total_in_trip"] = text
    reply_keyboard = [[CANCEL_TEXT]]
    await update.message.reply_text(
        "Шаг 5 из 9: **Укажите количество новых байков на линии («Новые байки на линии»)**:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    return NEW_BIKES

async def new_bikes_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == CANCEL_TEXT:
        return await cancel_report(update, context)

    context.user_data["report"]["new_bikes"] = text
    reply_keyboard = [[CANCEL_TEXT]]
    await update.message.reply_text(
        "Шаг 6 из 9: **Укажите количество старых байков на линии («Старые байки на линии»)**:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    return OLD_BIKES

async def old_bikes_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == CANCEL_TEXT:
        return await cancel_report(update, context)

    context.user_data["report"]["old_bikes"] = text
    reply_keyboard = [[CANCEL_TEXT]]
    await update.message.reply_text(
        "Шаг 7 из 9: **Укажите количество сломанных байков («Количество сломанных байков»)**:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    return BROKEN_BIKES

async def broken_bikes_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == CANCEL_TEXT:
        return await cancel_report(update, context)

    context.user_data["report"]["broken_bikes"] = text
    reply_keyboard = [[CANCEL_TEXT]]
    await update.message.reply_text(
        "Шаг 8 из 9: **Опишите причины возврата байков («Причины возврата байков»)**:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    return REASONS

async def reasons_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == CANCEL_TEXT:
        return await cancel_report(update, context)

    context.user_data["report"]["return_reasons"] = text
    reply_keyboard = [[SKIP_TEXT], [CANCEL_TEXT]]
    await update.message.reply_text(
        "Шаг 9 из 9: **Введите комментарий** (если есть необходимость) или нажмите «Пропустить»:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    return COMMENT

async def comment_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == CANCEL_TEXT:
        return await cancel_report(update, context)

    if text == SKIP_TEXT:
        comment = "-"
    else:
        comment = text

    context.user_data["report"]["comment"] = comment

    return await show_summary(update, context)

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rep = context.user_data.get("report", {})
    summary = (
        "📋 **Проверьте данные вашего отчёта «Байки»:**\n\n"
        f"📅 **Дата:** {rep.get('report_date')}\n"
        f"📤 **Выдано:** {rep.get('issued')}\n"
        f"📥 **Вернули:** {rep.get('returned')}\n"
        f"🚴 **Всего в поездке:** {rep.get('total_in_trip')}\n"
        f"🆕 **Новые байки на линии:** {rep.get('new_bikes')}\n"
        f"🚴‍♂️ **Старые байки на линии:** {rep.get('old_bikes')}\n"
        f"🛠 **Сломанных байков:** {rep.get('broken_bikes')}\n"
        f"📝 **Причины возврата:** {rep.get('return_reasons')}\n"
        f"💬 **Комментарий:** {rep.get('comment')}\n\n"
        "Отправить отчёт?"
    )

    reply_keyboard = [
        [CONFIRM_TEXT],
        [RESTART_TEXT, CANCEL_TEXT]
    ]

    await update.message.reply_text(
        summary,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    return CONFIRM

async def confirm_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == CANCEL_TEXT:
        return await cancel_report(update, context)

    if text == RESTART_TEXT:
        return await start_report(update, context)

    if text == CONFIRM_TEXT:
        user = update.effective_user
        rep = context.user_data.get("report", {})
        rep["user_id"] = user.id if user else None
        rep["username"] = user.full_name or user.username or f"User_{user.id}" if user else "Partner"
        rep["created_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Save to SQLite database
        saved_report = add_bike_report(rep, db_path=DB_PATH)

        # 2. Sync to Google Sheets if available
        sheets_sync = context.bot_data.get("sheets_sync")
        if sheets_sync:
            try:
                sheets_sync.append_bike_report(saved_report)
            except Exception as e:
                logger.error(f"Failed to sync report to Google Sheets: {e}")

        await update.message.reply_text(
            f"🎉 **Отчёт «Байки» успешно отправлен!**\n\nID отчёта в базе: `#{saved_report.get('id')}`\nСпасибо за работу!",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        context.user_data.pop("report", None)
        return ConversationHandler.END

    return CONFIRM

async def cancel_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("report", None)
    await update.message.reply_text(
        "❌ Заполнение отчёта отменено.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END

async def list_reports_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reports = get_bike_reports(limit=10, db_path=DB_PATH)
    if not reports:
        await update.message.reply_text("📭 В базе пока нет отправленных отчётов.")
        return

    text = "📋 **Последние 10 отчётов «Байки»:**\n\n"
    for r in reports:
        text += (
            f"🔹 **Отчёт #{r['id']}** ({r['report_date']})\n"
            f"👤 От: {r['username']}\n"
            f"📊 Выдано: {r['issued']} | Вернули: {r['returned']} | В поездке: {r['total_in_trip']}\n"
            f"🚴 Новые: {r['new_bikes']} | Старые: {r['old_bikes']} | Сломано: {r['broken_bikes']}\n"
            f"📝 Причины: {r['return_reasons']}\n"
            f"💬 Комментарий: {r['comment']}\n"
            f"🕒 Время: {r['created_at']}\n\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")

bike_report_conversation_handler = ConversationHandler(
    entry_points=[
        CommandHandler(["report", "bikes"], start_report),
        MessageHandler(filters.Regex(r"^(📝 Заполнить отчёт.*|/байки|/отчет|/отчёт|Заполнить отчёт|Байки)$"), start_report),
    ],

    states={
        REPORT_DATE: [MessageHandler(filters.TEXT & (~filters.COMMAND), date_step)],
        ISSUED: [MessageHandler(filters.TEXT & (~filters.COMMAND), issued_step)],
        RETURNED: [MessageHandler(filters.TEXT & (~filters.COMMAND), returned_step)],
        TOTAL_IN_TRIP: [MessageHandler(filters.TEXT & (~filters.COMMAND), total_in_trip_step)],
        NEW_BIKES: [MessageHandler(filters.TEXT & (~filters.COMMAND), new_bikes_step)],
        OLD_BIKES: [MessageHandler(filters.TEXT & (~filters.COMMAND), old_bikes_step)],
        BROKEN_BIKES: [MessageHandler(filters.TEXT & (~filters.COMMAND), broken_bikes_step)],
        REASONS: [MessageHandler(filters.TEXT & (~filters.COMMAND), reasons_step)],
        COMMENT: [MessageHandler(filters.TEXT & (~filters.COMMAND), comment_step)],
        CONFIRM: [MessageHandler(filters.TEXT & (~filters.COMMAND), confirm_step)],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_report),
        MessageHandler(filters.Regex(r"^❌ Отмена$"), cancel_report),
    ],
)
