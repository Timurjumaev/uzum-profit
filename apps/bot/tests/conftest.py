"""Bot testlari API test yordamchilarini (vaqtinchalik baza, tashkilot, soxta Uzum) qayta ishlatadi."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "api" / "tests"))
os.environ.setdefault("UP_OTP_PER_IP_HOUR", "100000")
