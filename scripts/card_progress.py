"""从题卡历史派生红绿灯轨迹；不创建作答记录，不推断未记录的表现。"""
import re

from card_history import history_entries

LIGHTS = {"不会": "🔴", "半会": "🟡", "会": "🟢"}
TARGET = 3
START = "<!-- review-progress:start -->"
END = "<!-- review-progress:end -->"
PROGRESS_RE = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)


def card_progress(body):
    entries = history_entries(body)
    streak = 0
    for entry in reversed(entries):
        if entry["status"] != "会":
            break
        streak += 1
    passed = streak >= TARGET
    progress = min(streak, TARGET)
    label = ("✅ 已过关" if passed else "待巩固") if entries else "待记录"
    return {
        "trajectory": " → ".join(LIGHTS[e["status"]] for e in entries),
        "attempts": len(entries),
        "green_streak": streak,
        "passed": passed,
        "summary": f"{progress} / {TARGET} · {label}" if entries else "未知 / 3 · 待记录",
    }


def render_progress(body):
    progress = card_progress(body)
    return (f"{START}\n"
            f"> **做题轨迹：** {progress['trajectory'] or '暂无历史记录'}\n"
            f"> **当前连绿：** {progress['summary']}\n"
            f"{END}")


def upsert_card_progress(body):
    block = render_progress(body)
    if PROGRESS_RE.search(body):
        return PROGRESS_RE.sub(lambda _: block, body, count=1)
    # 标题下、题面前；兼容没有二级标题的旧卡。
    title = re.search(r"^## [^\n]*(?:\n|$)", body, re.M)
    if title:
        at = title.end()
        return body[:at] + "\n" + block + "\n" + ("" if body[at:].startswith("\n") else "\n") + body[at:]
    section = re.search(r"^### ", body, re.M)
    at = section.start() if section else 0
    return body[:at] + block + "\n\n" + body[at:]
