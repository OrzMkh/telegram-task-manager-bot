import re
from datetime import datetime, timedelta

HASHTAGS = ["#задача", "#task", "#todo", "#задание"]
COMMANDS = [
    "/task", "/задача", "/add", "/newtask", "/todo",
    "задача:", "задача", "задачу:", "задачу", "task:", "task", "todo:"
]

def is_authorized_author(user) -> bool:
    """
    Rule 3: ONLY @orzmkh (Руководитель) is allowed to create and manage tasks.
    """
    if not user:
        return False
    username = (user.username or "").lower().replace("@", "").strip()
    return username == "orzmkh"


def is_recurring_task_message(text: str) -> bool:
    """
    Check if message starts with 'ЗП', 'зп', 'ZP', or 'zp' for Recurring Tasks.
    """
    if not text:
        return False
    text_stripped = text.strip()
    return bool(re.match(r"^[зzЗZ][пpПP](?:[\s:.,\-—]|(?=@)|$)", text_stripped))


def clean_recurring_task_text(text: str) -> str:
    """
    Cleans recurring task text by stripping leading 'ЗП'/'ZP' prefix.
    """
    cleaned = text.strip()
    trigger_prefix = re.match(r"^[зzЗZ][пpПP][\s:.,\-—]*", cleaned)
    if trigger_prefix:
        cleaned = cleaned[len(trigger_prefix.group(0)):].strip()
    return cleaned if cleaned else text


def is_task_message(text: str, user=None, has_explicit_command: bool = False) -> bool:
    """
    Rule 1: If message starts with 'З', 'Т', 'Z', or 'T' (case-insensitive) ONLY at the beginning,
    or explicit command /task, /задача, #task, create a task.
    Note: 'ЗП' / 'ZP' messages are handled separately as recurring tasks.
    """
    if not text:
        return False

    if is_recurring_task_message(text):
        return False

    if has_explicit_command:
        return True

    text_stripped = text.strip()
    text_lower = text_stripped.lower()

    # 1. Starts with commands or hashtags
    if any(text_lower.startswith(prefix) for prefix in ["/task", "/задача", "/add", "#task", "#задача", "#todo"]):
        return True

    # 2. Rule 1: Starts with letter 'З' / 'з', 'Т' / 'т', 'Z' / 'z', 'T' / 't' AT THE BEGINNING
    # Matches: "З ", "з ", "Т ", "т ", "Z ", "z ", "T ", "t ", "Т:", "т:", "Т.", "т.", "Т@", etc.
    trigger_pattern = r"^[зzЗZтtТT](?:[\s:.,\-—]|(?=@))"
    if re.match(trigger_pattern, text_stripped):
        return True

    return False



def extract_assignee(message) -> str:
    """
    Extract assignee based ONLY on explicit @mention(s) in message text or caption.
    Never takes replied message author automatically.
    If no @mention is present, returns empty string so bot can ask user to specify.
    """
    text = message.text or message.caption or ""
    mentions = re.findall(r"@[\w_]+", text)
    if mentions:
        return " ".join(mentions)
    return ""


def extract_author(message) -> str:
    if not message.from_user:
        return "Неизвестный"

    user = message.from_user
    if user.username:
        return f"@{user.username}"
    
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full_name if full_name else f"ID_{user.id}"


from config import get_now

MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
}

def extract_target_time(text: str) -> tuple[int, int] | None:
    t = text.lower()
    
    # "до 10 утра" / "10 утра" / "6 вечера"
    m = re.search(r"(?:до|в|к)?\s*(\d{1,2})\s*утра\b", t)
    if m:
        return (int(m.group(1)), 0)
        
    m = re.search(r"(?:до|в|к)?\s*(\d{1,2})\s*вечера\b", t)
    if m:
        hh = int(m.group(1))
        if hh < 12:
            hh += 12
        return (hh, 0)

    # "15:30", "15-00", "до 18:00"
    m = re.search(r"(?:до|в|к)?\s*(\d{1,2})[:\-.](\d{2})", t)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    # "до 18ч", "до 18 часов", "до 18"
    m = re.search(r"до\s+(\d{1,2})\s*(?:ч|час|часов)\b", t)
    if m:
        return (int(m.group(1)), 0)

    # Named time of day
    if any(w in t for w in ["к обеду", "до обеда", "в обед", "на обед", "обеду"]):
        return (13, 0)
    if any(w in t for w in ["к утру", "с утра", "утром", "до утра"]):
        return (10, 0)
    if "после обеда" in t:
        return (15, 0)
    if any(w in t for w in ["к вечеру", "вечером", "до вечера"]):
        return (18, 0)
    if any(w in t for w in ["до конца дня", "к концу дня", "до конца смены", "сегодня вечером"]):
        return (21, 0)
    if any(w in t for w in ["к ночи", "до ночи", "ночью"]):
        return (23, 0)
        
    return None

def parse_sla_deadline(text: str, base_time: datetime = None) -> datetime:
    """
    Parses relative and absolute SLA descriptions from text with Tashkent timezone awareness.
    Supports complex combinations like:
    - "сделать через 2 дня к обеду" -> base_time + 2 days at 13:00
    - "через неделю в 15:30" -> base_time + 7 days at 15:30
    - "завтра до 10 утра" -> Tomorrow at 10:00
    - "до завтра 15:00" -> Tomorrow at 15:00
    - "через 3 часа" -> base_time + 3 hours
    - "срочно" / "ASAP" -> base_time + 2 hours
    - Default fallback -> base_time + 24 hours
    """
    if base_time is None:
        base_time = get_now()

    text_lower = text.lower().strip()

    # 1. Pure Relative: Minutes (e.g. через 30 минут)
    minutes_match = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:минут|минуты|минуту|мин)\b", text_lower)
    if minutes_match:
        minutes = int(minutes_match.group(1))
        return base_time + timedelta(minutes=minutes)

    # 2. Pure Relative: Hours (e.g. через 2 часа, 3 часа), but NOT if followed by "утра/вечера"
    hours_match = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:часов|часа|час|ч)\b", text_lower)
    if hours_match and not any(w in text_lower for w in ["утра", "вечера", "дня"]):
        hours = int(hours_match.group(1))
        return base_time + timedelta(hours=hours)

    # 3. Urgent / ASAP
    if any(w in text_lower for w in ["срочно", "asap", "быстро"]):
        return base_time + timedelta(hours=2)

    # Extract any explicit or named target time (HH:MM)
    explicit_time = extract_target_time(text_lower)

    # 4. Weeks (e.g. через неделю к обеду, через 2 недели в 15:00)
    weeks_match = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:недель|недели|неделю|нед)\b", text_lower)
    if weeks_match:
        weeks = int(weeks_match.group(1))
        target_date = base_time + timedelta(days=7 * weeks)
        hh, mm = explicit_time if explicit_time else (18, 0)
        return target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)

    if any(w in text_lower for w in ["через неделю", "в течение недели", "на неделю", "неделю"]):
        target_date = base_time + timedelta(days=7)
        hh, mm = explicit_time if explicit_time else (18, 0)
        return target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # 5. Days (e.g. сделать через 2 дня к обеду, через 3 дня до 15:00, через 2 дня)
    days_match = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:дней|дня|день|дн)\b", text_lower)
    if days_match:
        days = int(days_match.group(1))
        target_date = base_time + timedelta(days=days)
        hh, mm = explicit_time if explicit_time else (18, 0)
        return target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # 6. Послезавтра
    if "послезавтра" in text_lower:
        target_date = base_time + timedelta(days=2)
        hh, mm = explicit_time if explicit_time else (18, 0)
        return target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # 7. Завтра
    if "завтра" in text_lower:
        target_date = base_time + timedelta(days=1)
        hh, mm = explicit_time if explicit_time else (18, 0)
        return target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # 8. Specific calendar date (e.g. до 15 августа 18:00, до 15.08 к обеду)
    date_named_match = re.search(r"до\s+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)", text_lower)
    if date_named_match:
        day = int(date_named_match.group(1))
        mon = MONTHS_RU[date_named_match.group(2)]
        hh, mm = explicit_time if explicit_time else (18, 0)
        return datetime(year=base_time.year, month=mon, day=day, hour=hh, minute=mm, second=0, microsecond=0)

    date_num_match = re.search(r"до\s+(\d{1,2})[./](\d{1,2})", text_lower)
    if date_num_match:
        day = int(date_num_match.group(1))
        mon = int(date_num_match.group(2))
        hh, mm = explicit_time if explicit_time else (18, 0)
        return datetime(year=base_time.year, month=mon, day=day, hour=hh, minute=mm, second=0, microsecond=0)

    # 9. Standalone time today or tomorrow (e.g. к обеду, до 10 утра, в 15:30)
    if explicit_time:
        hh, mm = explicit_time
        target_today = base_time.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target_today > base_time:
            return target_today
        return target_today + timedelta(days=1)

    # 10. Default fallback: +24 hours from current Tashkent time
    return base_time + timedelta(hours=24)




def clean_task_text(text: str) -> str:
    """
    Cleans task text by removing leading 'З'/'Т'/'Z'/'T' trigger, bot command prefixes or hashtags.
    """
    cleaned = text.strip()

    # 1. Clean leading 'З'/'Т'/'Z'/'T' prefix
    trigger_prefix = re.match(r"^[зzЗZтtТT][\s:.,\-—]*", cleaned)
    if trigger_prefix:
        cleaned = cleaned[len(trigger_prefix.group(0)):].strip()

    # 2. Remove command prefixes if present
    for cmd in COMMANDS:
        if cleaned.lower().startswith(cmd):
            cleaned = cleaned[len(cmd):].strip()
            break

    # 3. Remove hashtags if at start or end
    for tag in HASHTAGS:
        cleaned = re.sub(re.escape(tag), "", cleaned, flags=re.IGNORECASE)

    cleaned = cleaned.strip()
    return cleaned if cleaned else text
