import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from task_handlers import (
    generate_calendar_keyboard,
    generate_time_keyboard,
    get_sla_keyboard
)

class TestInteractiveSLA(unittest.TestCase):
    def test_sla_presets_keyboard(self):
        keyboard = get_sla_keyboard("12345")
        self.assertIsNotNone(keyboard)
        self.assertTrue(len(keyboard.inline_keyboard) >= 4)
        
        # Verify button callbacks
        first_row = keyboard.inline_keyboard[0]
        self.assertEqual(first_row[0].text, "⚡ 1 час")
        self.assertEqual(first_row[0].callback_data, "sla_preset_1h_12345")
        
        second_row = keyboard.inline_keyboard[1]
        self.assertEqual(second_row[0].text, "🌇 До конца дня (18:00)")
        self.assertEqual(second_row[0].callback_data, "sla_preset_today18_12345")

    def test_calendar_keyboard_generation(self):
        # Generate calendar for August 2026
        keyboard = generate_calendar_keyboard(2026, 8, "12345")
        self.assertIsNotNone(keyboard)
        
        # August 2026 starts on Saturday (5th day in monthcalendar if Mon is index 0)
        # Weekdays header row, month header row, and month weeks + navigation row
        # Check rows
        self.assertTrue(len(keyboard.inline_keyboard) > 3)
        
        # Check headers
        month_header = keyboard.inline_keyboard[0][0]
        self.assertEqual(month_header.text, "Август 2026")
        self.assertEqual(month_header.callback_data, "cal_ignore_12345")
        
        # Check day buttons
        third_row = keyboard.inline_keyboard[2] # Monday through Sunday buttons of week 1
        # Day 1 of August 2026 is Saturday, so index 5
        self.assertEqual(third_row[5].text, "1")
        self.assertEqual(third_row[5].callback_data, "cal_day_2026_8_1_12345")
        
        # Check navigation
        nav_row = keyboard.inline_keyboard[-1]
        self.assertEqual(nav_row[0].text, "◀️")
        self.assertEqual(nav_row[0].callback_data, "cal_nav_2026_7_12345")
        self.assertEqual(nav_row[2].text, "▶️")
        self.assertEqual(nav_row[2].callback_data, "cal_nav_2026_9_12345")

    def test_time_keyboard_generation(self):
        keyboard = generate_time_keyboard(2026, 8, 15, "12345")
        self.assertIsNotNone(keyboard)
        
        # Check some time slot
        first_row = keyboard.inline_keyboard[0]
        self.assertEqual(first_row[0].text, "08:00")
        self.assertEqual(first_row[0].callback_data, "cal_time_2026_8_15_08_00_12345")
        
        # Back button
        back_btn = keyboard.inline_keyboard[-1][0]
        self.assertEqual(back_btn.text, "◀️ Назад к календарю")
        self.assertEqual(back_btn.callback_data, "cal_nav_2026_8_12345")

if __name__ == "__main__":
    unittest.main()
