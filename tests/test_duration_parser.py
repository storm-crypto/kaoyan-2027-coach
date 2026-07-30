from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from duration_parser import parse_logged_hours  # noqa: E402


def test_parse_plain_hours_and_decimal():
    assert parse_logged_hours("- **时长**: 8") == 8
    assert parse_logged_hours("- **时长**: 3.5h") == 3.5


def test_parse_hours_and_minutes():
    assert abs(parse_logged_hours("- **时长**: 5h47min") - (5 + 47 / 60)) < 1e-9
    assert abs(parse_logged_hours("- **时长**: 1小时22分钟") - (1 + 22 / 60)) < 1e-9


def test_parse_minutes_without_treating_them_as_hours():
    assert abs(parse_logged_hours("- **时长**: 50min") - 50 / 60) < 1e-9
    assert abs(parse_logged_hours("- **时长**: 26分钟") - 26 / 60) < 1e-9


def test_parse_subject_prefixed_duration():
    assert parse_logged_hours("- **时长**: 数学一=8h") == 8


def test_missing_or_unrecorded_duration_is_zero():
    assert parse_logged_hours("- **时长**: 未记录") == 0
    assert parse_logged_hours("没有时长字段") == 0
