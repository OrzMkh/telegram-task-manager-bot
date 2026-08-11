import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from task_detector import parse_sla_deadline
from config import get_now

base = get_now()
print("Base Tashkent Time:", base.strftime("%Y-%m-%d %H:%M:%S"))

tests = [
    "З @isslamov проверить байки через 3 часа",
    "З @axi0603 подготовить отчет до завтра 15:00",
    "З @axi0603 сделать до вечера",
    "З @isslamov проверить кассу до 22:00",
    "З @axi0603 срочно починить сервер",
    "З @isslamov тест 30 минут",
    "З @axi0603 просто задача без времени"
]

for test in tests:
    sla = parse_sla_deadline(test, base_time=base)
    print(f"Text: '{test}' -> SLA: {sla.strftime('%Y-%m-%d %H:%M:%S')}")
