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


def is_task_message(text: str, user=None, has_explicit_command: bool = False) -> bool:
    """
    Rule 1: If message starts with 'З', 'Т', 'Z', or 'T' (case-insensitive) ONLY at the beginning,
    or explicit command /task, /задача, #task, create a task.
    """
    if not text:
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

def parse_sla_deadline(text: str, base_time: datetime = None) -> datetime:
    """
    Parses relative and absolute SLA descriptions from text with Tashkent timezone awareness:
    - "через 30 минут", "30 мин" -> base_time + 30m
    - "через 3 часа", "3 часа", "3ч" -> base_time + 3h
    - "до завтра 15:00" -> Tomorrow at 15:00
    - "до завтра" -> Tomorrow at 18:00
    - "до послезавтра" -> +2 days at 18:00
    - "до конца дня" / "до вечера" -> Today 21:00 (or +3h if late)
    - "срочно" / "ASAP" -> +2 hours
    - "до 18:00" / "до 18-00" -> Today 18:00 (or Tomorrow 18:00 if already past)
    - "до 15.08 18:00" / "до 15 августа" -> Specific date
    - Default fallback -> base_time + 24 hours
    """
    if base_time is None:
        base_time = get_now()

    text_lower = text.lower().strip()

    # 1. Pattern: "минут" (e.g. "через 30 минут", "в течение 45 мин", "30 минут", "30мин")
    minutes_match = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:минут|минуты|минуту|мин)\b", text_lower)
    if minutes_match:
        minutes = int(minutes_match.group(1))
        return base_time + timedelta(minutes=minutes)

    # 2. Pattern: "часов" / "ч" (e.g. "через 2 часа", "в течение 3 часов", "2 часа", "2ч")
    hours_match = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:часов|часа|час|ч)\b", text_lower)
    if hours_match:
        hours = int(hours_match.group(1))
        return base_time + timedelta(hours=hours)

    # 3. Pattern: "дней" / "дня" / "день"
    days_match = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:дней|дня|день|дн)\b", text_lower)
    if days_match:
        days = int(days_match.group(1))
        return base_time + timedelta(days=days)

    # 4. Pattern: "срочно" / "asap" / "быстро"
    if any(w in text_lower for w in ["срочно", "asap", "быстро"]):
        return base_time + timedelta(hours=2)

    # 5. Pattern: Weeks (e.g. "через неделю", "через 2 недели", "на неделю", "в течение недели")
    weeks_match = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:недель|недели|неделю|нед)\b", text_lower)
    if weeks_match:
        weeks = int(weeks_match.group(1))
        return base_time + timedelta(days=7 * weeks)
    if any(w in text_lower for w in ["через неделю", "в течение недели", "на неделю", "неделю"]):
        return base_time + timedelta(days=7)

    # 5b. Pattern: Months (e.g. "через месяц", "через 2 месяца")
    months_match = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:месяцев|месяца|месяц)\b", text_lower)
    if months_match:
        months_cnt = int(months_match.group(1))
        return base_time + timedelta(days=30 * months_cnt)
    if "через месяц" in text_lower or "в течение месяца" in text_lower:
        return base_time + timedelta(days=30)


    # 6. Pattern: "до конца дня" / "до вечера" / "до конца смены"
    if any(w in text_lower for w in ["до конца дня", "до вечера", "до конца смены", "сегодня вечером"]):
        if base_time.hour < 21:
            return base_time.replace(hour=21, minute=0, second=0, microsecond=0)
        return base_time + timedelta(hours=3)

    # 7. Pattern: "до послезавтра"
    after_tomorrow_match = re.search(r"до послезавтра(?:\s+(?:в|до)?\s*(\d{1,2})(?:[:\-.](\d{2}))?)?", text_lower)
    if after_tomorrow_match:
        hh = int(after_tomorrow_match.group(1)) if after_tomorrow_match.group(1) else 18
        mm = int(after_tomorrow_match.group(2)) if after_tomorrow_match.group(2) else 0
        return (base_time + timedelta(days=2)).replace(hour=hh, minute=mm, second=0, microsecond=0)

    # 8. Pattern: "до завтра"
    tomorrow_match = re.search(r"до завтра(?:\s+(?:в|до)?\s*(\d{1,2})(?:[:\-.](\d{2}))?)?", text_lower)
    if tomorrow_match:
        hh = int(tomorrow_match.group(1)) if tomorrow_match.group(1) else 18
        mm = int(tomorrow_match.group(2)) if tomorrow_match.group(2) else 0
        return (base_time + timedelta(days=1)).replace(hour=hh, minute=mm, second=0, microsecond=0)

    # 9. Pattern: Specific month name date (e.g. "до 15 августа 18:00", "до 25 мая")
    date_named_match = re.search(r"до\s+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+(?:в|до)?\s*(\d{1,2})[:\-.](\d{2}))?", text_lower)
    if date_named_match:
        day = int(date_named_match.group(1))
        mon = MONTHS_RU[date_named_match.group(2)]
        hh = int(date_named_match.group(3)) if date_named_match.group(3) else 18
        mm = int(date_named_match.group(4)) if date_named_match.group(4) else 0
        target_year = base_time.year
        return datetime(year=target_year, month=mon, day=day, hour=hh, minute=mm, second=0, microsecond=0)

    # 10. Pattern: Specific numerical date (e.g. "до 15.08 18:00", "до 25/08")
    date_num_match = re.search(r"до\s+(\d{1,2})[./](\d{1,2})(?:\s+(?:в|до)?\s*(\d{1,2})[:\-.](\d{2}))?", text_lower)
    if date_num_match:
        day = int(date_num_match.group(1))
        mon = int(date_num_match.group(2))
        hh = int(date_num_match.group(3)) if date_num_match.group(3) else 18
        mm = int(date_num_match.group(4)) if date_num_match.group(4) else 0
        target_year = base_time.year
        return datetime(year=target_year, month=mon, day=day, hour=hh, minute=mm, second=0, microsecond=0)

    # 11. Pattern: Specific time today/tomorrow (e.g. "до 18:00", "до 18-00", "до 18.30", "до 18ч", "до 18 часов")
    time_match = re.search(r"до\s+(\d{1,2})(?:[:\-.](\d{2})|\s*(?:ч|час|часов)\b)", text_lower)
    if time_match:
        hh = int(time_match.group(1))
        mm = int(time_match.group(2)) if time_match.group(2) else 0
        target_today = base_time.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target_today > base_time:
            return target_today
        else:
            return target_today + timedelta(days=1)

    # 12. Default fallback: +24 hours from current Tashkent time
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
