import re
from datetime import datetime, timedelta

NLP_KEYWORDS = [
    r"\bнужно\b", r"\bсделать\b", r"\bпроверь\b", r"\bпоправь\b",
    r"\bподготовь\b", r"\bнапиши\b", r"\bсоздай\b", r"\bотправь\b",
    r"\bдоделай\b", r"\bисправь\b", r"\bнастрой\b", r"\bсделай\b",
    r"\bfix\b", r"\btodo\b"
]

HASHTAGS = ["#задача", "#task", "#todo"]
COMMANDS = ["/task", "/задача", "/add"]

def has_explicit_sla(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    patterns = [
        r"\b(?:в течение|через)\s+\d+\s*(?:ч|час|часа|часов|д|день|дня|дней|мин|минут|минуты)\b",
        r"\bдо завтра\b",
        r"\bдо\s+\d{1,2}[:\-.]\d{2}\b",
        r"\bsla\s*[:\-=]?\s*\d+",
        r"\bсрок\s*[:\-=]?\s*\d+",
        r"\b\d+\s*(?:ч|час|часа|часов|дней|дня|дний|д)\b",
        r"\bдо\s+\d{1,2}\.\d{2}\b"
    ]
    for p in patterns:
        if re.search(p, text_lower):
            return True
    return False

def is_task_message(text: str, user=None, has_explicit_command: bool = False) -> bool:
    if not text:
        return False

    # 1. Author check: ONLY process messages from @orzmkh
    if user:
        username = getattr(user, "username", "") or ""
        if username.lower() != "orzmkh":
            return False

    text_lower = text.lower().strip()

    # 2. Keyword check: MUST contain 'задача', 'задачу', '/task', '/задача', '#задача'
    has_task_kw = any(kw in text_lower for kw in ["задача", "задачу", "/task", "/задача", "#задача", "#task"])
    if not has_task_kw and not has_explicit_command:
        return False

    # 3. SLA check: MUST specify explicit SLA/deadline
    if not has_explicit_sla(text_lower) and not has_explicit_command:
        return False

    return True


def extract_assignee(message) -> str:
    """
    Extract assignee based on reply -> @mention -> default 'Команда'.
    """
    # 1. Reply to another user
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
        if target_user.username:
            return f"@{target_user.username}"
        full_name = f"{target_user.first_name or ''} {target_user.last_name or ''}".strip()
        return full_name if full_name else f"ID_{target_user.id}"

    # 2. Mention in text (@username)
    text = message.text or message.caption or ""
    mentions = re.findall(r"@[\w_]+", text)
    if mentions:
        return mentions[0]

    # 3. Default fallback
    return "Команда"


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
    Cleans task text by removing bot command prefixes or task hashtags.
    """
    cleaned = text
    # Remove command prefix
    for cmd in COMMANDS:
        if cleaned.lower().startswith(cmd):
            cleaned = cleaned[len(cmd):].strip()
            break

    # Remove hashtags if at start or end
    for tag in HASHTAGS:
        cleaned = re.sub(re.escape(tag), "", cleaned, flags=re.IGNORECASE)

    cleaned = cleaned.strip()
    return cleaned if cleaned else text
