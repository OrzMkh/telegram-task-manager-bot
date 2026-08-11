import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from datetime import datetime, timedelta, timezone

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

def parse_sla(text: str, base_time: datetime) -> datetime:
    t = text.lower().strip()

    # 1. Pure Relative: Minutes (e.g. через 30 минут)
    m = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:минут|минуты|минуту|мин)\b", t)
    if m:
        return base_time + timedelta(minutes=int(m.group(1)))

    # 2. Pure Relative: Hours (e.g. через 2 часа, 3 часа), but NOT if followed by "утра/вечера"
    m = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:часов|часа|час|ч)\b", t)
    if m and not any(w in t for w in ["утра", "вечера", "дня"]):
        return base_time + timedelta(hours=int(m.group(1)))

    # 3. Urgent / ASAP
    if any(w in t for w in ["срочно", "asap", "быстро"]):
        return base_time + timedelta(hours=2)

    # Extract any explicit or named target time (HH:MM)
    explicit_time = extract_target_time(t)

    # 4. Weeks (e.g. через неделю к обеду, через 2 недели в 15:00)
    m_weeks = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:недель|недели|неделю|нед)\b", t)
    if m_weeks:
        weeks = int(m_weeks.group(1))
        target_date = base_time + timedelta(days=7 * weeks)
        hh, mm = explicit_time if explicit_time else (18, 0)
        return target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)

    if any(w in t for w in ["через неделю", "в течение недели", "на неделю", "неделю"]):
        target_date = base_time + timedelta(days=7)
        hh, mm = explicit_time if explicit_time else (18, 0)
        return target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # 5. Days (e.g. сделать через 2 дня к обеду, через 3 дня до 15:00, через 2 дня)
    m_days = re.search(r"(?:в течение|через|\b)(\d+)\s*(?:дней|дня|день|дн)\b", t)
    if m_days:
        days = int(m_days.group(1))
        target_date = base_time + timedelta(days=days)
        hh, mm = explicit_time if explicit_time else (18, 0)
        return target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # 6. Послезавтра
    if "послезавтра" in t:
        target_date = base_time + timedelta(days=2)
        hh, mm = explicit_time if explicit_time else (18, 0)
        return target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # 7. Завтра
    if "завтра" in t:
        target_date = base_time + timedelta(days=1)
        hh, mm = explicit_time if explicit_time else (18, 0)
        return target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # 8. Specific calendar date (e.g. до 15 августа 18:00, до 15.08 к обеду)
    m_date = re.search(r"до\s+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)", t)
    if m_date:
        day = int(m_date.group(1))
        mon = MONTHS_RU[m_date.group(2)]
        hh, mm = explicit_time if explicit_time else (18, 0)
        return datetime(year=base_time.year, month=mon, day=day, hour=hh, minute=mm, second=0, microsecond=0)

    m_num_date = re.search(r"до\s+(\d{1,2})[./](\d{1,2})", t)
    if m_num_date:
        day = int(m_num_date.group(1))
        mon = int(m_num_date.group(2))
        hh, mm = explicit_time if explicit_time else (18, 0)
        return datetime(year=base_time.year, month=mon, day=day, hour=hh, minute=mm, second=0, microsecond=0)

    # 9. Standalone time today or tomorrow (e.g. к обеду, до 10 утра, в 15:30)
    if explicit_time:
        hh, mm = explicit_time
        target_today = base_time.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target_today > base_time:
            return target_today
        return target_today + timedelta(days=1)

    # 10. Default fallback: +24 hours
    return base_time + timedelta(hours=24)

# Test base time: 2026-08-11 20:18:00
base = datetime(2026, 8, 11, 20, 18, 0)
print(f"Base Time: {base.strftime('%Y-%m-%d %H:%M:%S')}\n")

test_cases = [
    "сделать через 2 дня к обеду",
    "сделать завтра к обеду",
    "завтра до 10 утра надо сделать",
    "через 3 дня в 15:30",
    "через неделю к утру",
    "через 2 дня к вечеру",
    "проверить кассу через 3 часа",
    "отчет через 30 минут",
    "срочно починить бота",
    "просто задача без дедлайна"
]

for tc in test_cases:
    res = parse_sla(tc, base)
    print(f"'{tc}' -> {res.strftime('%Y-%m-%d %H:%M:%S')}")
