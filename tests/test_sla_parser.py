import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from task_detector import parse_sla_deadline
from config import get_now

base = get_now()
print("Base Tashkent Time:", base.strftime("%Y-%m-%d %H:%M:%S"))

phrases = [
    "сделать надо завтра к обеду",
    "нужно сделать завтра с утра",
    "завтра после обеда",
    "завтра к вечеру",
    "сделать к обеду",
    "послезавтра к обеду",
    "нужно сделать ровно через неделю тест"
]

for p in phrases:
    sla = parse_sla_deadline(p, base)
    fmt = sla.strftime("%Y-%m-%d %H:%M:%S")
    print(f"'{p}' -> {fmt}")
