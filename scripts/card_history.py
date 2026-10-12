"""错题卡历史的只读解析；首次归档不重复算作复习。"""
import re
from datetime import date

from archive_ops import extract_heading_block
from env_util import safe_int


def history_entries(body):
    entries = []
    block = extract_heading_block(body, "历史记录", level=3)
    for line in block.splitlines():
        match = re.match(r"^-\s*(\d{4}-\d{2}-\d{2})\s*-\s*(不会|半会|会)\s*-\s*(.*)$", line.strip())
        if not match:
            continue
        try:
            day = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        entries.append({"date": day, "status": match.group(2), "comment": match.group(3),
                        "marker": line.strip()})
    return entries


def first_wrong_day(card):
    try:
        return date.fromisoformat(str(card["frontmatter"].get("first_wrong_at", "")))
    except ValueError:
        return None


def error_events(card):
    first = first_wrong_day(card)
    events = [(first, "first")] if first else []
    initial_seen = False
    seen = set()
    for entry in history_entries(card["body"]):
        if entry["marker"] in seen:
            continue
        seen.add(entry["marker"])
        if entry["date"] == first and not initial_seen:
            initial_seen = True
            continue
        if entry["status"] != "会":
            events.append((entry["date"], entry["marker"]))
    return sorted(events)


def consecutive_failures(frontmatter, body):
    """缓存字段优先；旧卡只从复习历史回算，不使用 wrong_count。"""
    if "consecutive_failures" in frontmatter:
        return max(safe_int(frontmatter["consecutive_failures"], 0), 0)
    entries = history_entries(body)
    if entries and entries[0]["date"].isoformat() == str(frontmatter.get("first_wrong_at", "")):
        entries = entries[1:]  # 新建不是一次复习。
    count = 0
    for entry in reversed(entries):
        if entry["status"] != "不会":
            break
        count += 1
    return count
