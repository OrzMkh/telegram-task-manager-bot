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


def parse_sla_deadline(text: str, base_time: datetime = None) -> datetime:
    """
    Parses relative SLA descriptions from text:
    - "до завтра 15:00" -> Tomorrow at 15:00
    - "до завтра" -> Tomorrow at 18:00
    - "в течение X часов" / "через X часов" -> base_time + X hours
    - "до 18:00" -> Today 18:00 (or Tomorrow 18:00 if past)
    - Default -> base_time + 24 hours
    """
    if base_time is None:
        base_time = datetime.now()

    text_lower = text.lower()

    # Pattern: "в течение X часов / ч" or "через X часов / ч"
    hours_match = re.search(r"(?:в течение|через)\s+(\d+)\s*(?:часов|часа|час|ч)", text_lower)
    if hours_match:
        hours = int(hours_match.group(1))
        return base_time + timedelta(hours=hours)

    # Pattern: "до завтра 15:00" or "до завтра в 15:00" or "до завтра 15-00"
    tomorrow_time_match = re.search(r"до завтра(?:\s+в)?\s+(\d{1,2})[:\-.](\d{2})", text_lower)
    if tomorrow_time_match:
        hh = int(tomorrow_time_match.group(1))
        mm = int(tomorrow_time_match.group(2))
        tomorrow = base_time + timedelta(days=1)
        return tomorrow.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # Pattern: "до завтра" (default to 18:00)
    if "до завтра" in text_lower:
        tomorrow = base_time + timedelta(days=1)
        return tomorrow.replace(hour=18, minute=0, second=0, microsecond=0)

    # Pattern: "до 18:00" or "до 18-00" or "до 18:30"
    time_match = re.search(r"до\s+(\d{1,2})[:\-.](\d{2})", text_lower)
    if time_match:
        hh = int(time_match.group(1))
        mm = int(time_match.group(2))
        target_today = base_time.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target_today > base_time:
            return target_today
        else:
            return target_today + timedelta(days=1)

    # Default fallback: +24 hours
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
