"""考研驾驶舱的纯数据层:把档案/日志/错题/报告归一化成 JSON payload。

build_dashboard.py 的渲染层不应直接读盘——所有 IO 都收口在这里,
方便单测、复用,以及未来换其它输出形式(MCP / 其它前端)时直接替换。
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from archive_ops import (
    extract_heading_block,
    extract_list_items,
    infer_subject_mentions,
    parse_mock_rows,
    parse_score_cell,
    parse_subject_score_rows,
    safe_load_archive_text,
)
from constants import PLAN_SUBJECTS, SCORE_SUBJECTS, SRS_GRADUATED_INTERVAL_DAYS, SUBJECT_META
from frontmatter import parse_frontmatter
from score_record_lib import collect_score_records, top_weakness_from_408_record
from study_ops import iter_review_cards


SUBJECT_TO_KM_FILE = {
    "数学一": "数学一.md",
    "408": "408.md",
    "英语一": "英语一.md",
    "政治": "政治.md",
}
SUBJECT_ALIAS_TEXT = {
    "数学一": ("数学一", "数学", "高数", "线代", "概率"),
    "408": ("408", "数据结构", "组成原理", "操作系统", "计算机网络", "计网", "计组"),
    "英语一": ("英语一", "英语", "阅读", "翻译", "写作", "完形"),
    "政治": ("政治", "马原", "毛中特", "史纲", "思修", "时政"),
}
STATUS_ORDER = ("不会", "半会", "会")
HISTORY_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) - (不会|半会|会) -", re.M)
EXAM_DATE_RE = re.compile(r"考试日期\*\*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")
UPDATE_DATE_RE = re.compile(r"最近更新日期\*\*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")
STAGE_RE = re.compile(r"当前阶段关键词\*\*[:：]\s*(.+)")
LOG_HOURS_RE = re.compile(r"时长[^0-9]*([0-9]+(?:\.[0-9]+)?)")


def safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def parse_iso_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_number(value: str) -> Optional[float]:
    match = re.search(r"[-+]?[0-9]+(?:\.[0-9]+)?", value or "")
    return float(match.group(0)) if match else None


def format_number(value: Optional[float]) -> str:
    if value is None:
        return "-"
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f"{value:.1f}"


def format_date(value: Optional[date]) -> str:
    return value.isoformat() if value else "-"


def parse_archive_progress(archive_text: str) -> Dict[str, Dict[str, object]]:
    block = extract_heading_block(archive_text, "各科当前状态", level=2)
    rows: Dict[str, Dict[str, object]] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
        if len(cells) != 5 or cells[0] == "科目" or set(cells[0]) == {"-"}:
            continue
        subject = cells[0]
        current = parse_number(cells[1])
        target = parse_number(cells[2])
        computed_gap = None
        if current is not None and target is not None:
            computed_gap = target - current
        else:
            computed_gap = parse_number(cells[3])
        rows[subject] = {
            "subject": subject,
            "current": current,
            "target": target,
            "gap": computed_gap,
            "judgement": cells[4],
        }
    return rows


def parse_archive_basic_info(archive_text: str, today: date) -> Dict[str, object]:
    exam_match = EXAM_DATE_RE.search(archive_text)
    update_match = UPDATE_DATE_RE.search(archive_text)
    stage_match = STAGE_RE.search(archive_text)
    exam_day = parse_iso_date(exam_match.group(1)) if exam_match else None
    latest_update = parse_iso_date(update_match.group(1)) if update_match else None
    return {
        "exam_date": format_date(exam_day),
        "days_until_exam": (exam_day - today).days if exam_day else None,
        "latest_archive_update": format_date(latest_update),
        "stage": stage_match.group(1).strip() if stage_match else "",
        "focus_problems": extract_list_items(archive_text, "最近聚焦问题（只保留 3-5 条）"),
        "next_steps": extract_list_items(archive_text, "下一步建议（只保留 3 条）"),
    }


def parse_log_entry(log_path: Path) -> Optional[Dict[str, object]]:
    log_day = parse_iso_date(log_path.stem)
    if log_day is None:
        return None
    text = safe_read_text(log_path)
    if not text:
        return None
    topic_match = re.search(r"\*\*主题\*\*:\s*(.+)", text)
    topic = topic_match.group(1).strip() if topic_match else ""
    hours_match = LOG_HOURS_RE.search(text)
    hours = float(hours_match.group(1)) if hours_match else None
    learned = extract_list_items(text, "学到了什么")
    blockers = extract_list_items(text, "卡壳与挣扎")
    review = extract_list_items(text, "下次需要复习")
    subject_counts = infer_subject_mentions([topic] + learned + blockers + review)
    return {
        "date": log_day,
        "topic": topic,
        "hours": hours,
        "path": str(log_path),
        "subject_counts": subject_counts,
    }


def collect_logs(obsidian_root: Path) -> List[Dict[str, object]]:
    log_dir = obsidian_root / "学习日志"
    if not log_dir.exists():
        return []
    entries = []
    for log_path in sorted(log_dir.glob("*.md")):
        entry = parse_log_entry(log_path)
        if entry:
            entries.append(entry)
    return entries


def compute_log_streak(log_dates: Sequence[date]) -> int:
    if not log_dates:
        return 0
    ordered = sorted(set(log_dates), reverse=True)
    streak = 1
    previous = ordered[0]
    for current in ordered[1:]:
        if previous - current == timedelta(days=1):
            streak += 1
            previous = current
            continue
        break
    return streak


def build_heatmap_series(days_with_counts: Mapping[date, int], today: date, span: int) -> List[Dict[str, object]]:
    start = today - timedelta(days=span - 1)
    cells = []
    for offset in range(span):
        current = start + timedelta(days=offset)
        count = days_with_counts.get(current, 0)
        level = 0
        if count >= 3:
            level = 3
        elif count == 2:
            level = 2
        elif count == 1:
            level = 1
        cells.append({
            "date": current.isoformat(),
            "count": count,
            "level": level,
            "weekday": current.weekday(),
        })
    return cells


def bucket_overdue_days(overdue_days: int) -> str:
    if overdue_days <= 0:
        return "今天到期"
    if overdue_days <= 3:
        return "超期 1-3 天"
    if overdue_days <= 7:
        return "超期 4-7 天"
    return "超期 8 天+"


def extract_card_history_statuses(body: str) -> List[str]:
    return [status for _, status in HISTORY_RE.findall(body)]


def collect_cards(obsidian_root: Path, today: date) -> List[Dict[str, object]]:
    wrongbook_root = obsidian_root / "错题本"
    cards: List[Dict[str, object]] = []
    if not wrongbook_root.exists():
        return cards

    for item in iter_review_cards(obsidian_root):
        if item["icloud_placeholder"]:
            continue
        fm = item["frontmatter"]
        if not fm or not fm.get("first_wrong_at"):
            continue
        path = item["path"]
        try:
            rel = path.relative_to(wrongbook_root)
        except ValueError:
            rel = path
        chapter_parts = list(rel.parts[1:-1]) if len(rel.parts) >= 3 else []
        chapter = " / ".join(chapter_parts) if chapter_parts else "未分类"
        created_at = parse_iso_date(str(fm.get("first_wrong_at", "")))
        last_review_at = parse_iso_date(str(fm.get("last_review_at", "")))
        next_review = item["next_review"]
        review_interval = item["review_interval"] or 0
        status = str(fm.get("status", "")).strip()
        overdue_days = None
        is_due = False
        if next_review is not None and review_interval < SRS_GRADUATED_INTERVAL_DAYS:
            overdue_days = (today - next_review).days
            is_due = next_review <= today
        history_statuses = extract_card_history_statuses(item["body"])
        promoted = any(history in {"半会", "会"} for history in history_statuses)
        cards.append({
            "path": str(path),
            "subject": item["subject"],
            "topic": str(fm.get("topic", item["topic"])).strip() or item["topic"],
            "chapter": chapter,
            "created_at": format_date(created_at),
            "last_review_at": format_date(last_review_at),
            "next_review": format_date(next_review),
            "review_interval": review_interval,
            "status": status or "未标注",
            "is_due": is_due,
            "overdue_days": overdue_days,
            "overdue_bucket": bucket_overdue_days(overdue_days) if overdue_days is not None else "未排期",
            "graduated": review_interval >= SRS_GRADUATED_INTERVAL_DAYS,
            "promoted": promoted,
        })
    return cards


def collect_knowledge_maps(obsidian_root: Path) -> Dict[str, Dict[str, object]]:
    km_root = obsidian_root / "知识地图"
    result: Dict[str, Dict[str, object]] = {}
    for subject in PLAN_SUBJECTS:
        km_path = km_root / SUBJECT_TO_KM_FILE[subject]
        data = {
            "subject": subject,
            "path": str(km_path),
            "exists": km_path.exists(),
            "total_topics": 0,
            "不会": 0,
            "半会": 0,
            "会": 0,
            "unmarked": 0,
            "marked_topics": 0,
        }
        if not km_path.exists():
            result[subject] = data
            continue

        text = safe_read_text(km_path)
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
            if len(cells) < 4 or cells[0] == "考点" or set(cells[0]) == {"-"}:
                continue
            topic_cell = cells[0]
            if not topic_cell or "**" in topic_cell:
                continue
            status = cells[1].strip()
            data["total_topics"] += 1
            if status in STATUS_ORDER:
                data[status] += 1
                data["marked_topics"] += 1
            else:
                data["unmarked"] += 1

        result[subject] = data
    return result


def parse_report_date_from_filename(filename: str) -> Optional[date]:
    mock_match = re.match(r"(\d{4}-\d{2}-\d{2})-模考分析\.md$", filename)
    if mock_match:
        return parse_iso_date(mock_match.group(1))
    week_match = re.match(r"(\d{4})-W(\d{2})-周复盘\.md$", filename)
    if week_match:
        return date.fromisocalendar(int(week_match.group(1)), int(week_match.group(2)), 7)
    month_match = re.match(r"(\d{4})-(\d{2})-月复盘\.md$", filename)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        if month == 12:
            return date(year, month, 31)
        next_month = date(year, month + 1, 1)
        return next_month - timedelta(days=1)
    return None


def collect_reports(obsidian_root: Path) -> Dict[str, object]:
    report_dir = obsidian_root / "复盘报告"
    mock_reports: List[Dict[str, object]] = []
    recap_reports: List[Dict[str, object]] = []
    recap_subject_counts = {subject: 0 for subject in PLAN_SUBJECTS}
    if not report_dir.exists():
        return {
            "mock_reports": mock_reports,
            "recap_reports": recap_reports,
            "recap_subject_counts": recap_subject_counts,
        }

    for report_path in sorted(report_dir.glob("*.md")):
        report_date = parse_report_date_from_filename(report_path.name)
        text = safe_read_text(report_path)
        if report_date is None:
            continue
        if report_path.name.endswith("-模考分析.md"):
            mock_reports.append({
                "date": report_date,
                "path": str(report_path),
            })
            continue

        counts = infer_subject_mentions(text.splitlines())
        for subject, count in counts.items():
            recap_subject_counts[subject] += count
        recap_reports.append({
            "date": report_date,
            "path": str(report_path),
            "subject_counts": counts,
        })

    return {
        "mock_reports": mock_reports,
        "recap_reports": recap_reports,
        "recap_subject_counts": recap_subject_counts,
    }


def collect_chapter_reports(obsidian_root: Path) -> Dict[str, object]:
    root = obsidian_root / "章节掌握报告" / "408"
    reports = []
    module_counts: Counter = Counter()
    if not root.exists():
        return {"reports": reports, "module_counts": module_counts}

    for report_path in sorted(root.rglob("*.md")):
        text = safe_read_text(report_path)
        if not text:
            continue
        fm, _, _ = parse_frontmatter(text)
        session_date = parse_iso_date(str(fm.get("session_date", "")))
        module = str(fm.get("module", "未标注模块")).strip() or "未标注模块"
        chapter = str(fm.get("chapter", report_path.stem)).strip() or report_path.stem
        mastery = str(fm.get("overall_mastery", "")).strip()
        reports.append({
            "date": format_date(session_date),
            "module": module,
            "chapter": chapter,
            "mastery": mastery,
            "path": str(report_path),
        })
        module_counts[module] += 1
    return {"reports": reports, "module_counts": dict(module_counts)}


def build_subject_logs_signal(logs: Sequence[Mapping[str, object]]) -> Dict[str, int]:
    counts = {subject: 0 for subject in PLAN_SUBJECTS}
    for entry in logs:
        for subject, value in entry["subject_counts"].items():
            counts[subject] += value
    return counts


def build_subject_card_counts(cards: Sequence[Mapping[str, object]]) -> Dict[str, int]:
    counts = {subject: 0 for subject in PLAN_SUBJECTS}
    for card in cards:
        if card["subject"] in counts:
            counts[card["subject"]] += 1
    return counts


def build_subject_due_counts(cards: Sequence[Mapping[str, object]]) -> Dict[str, int]:
    counts = {subject: 0 for subject in PLAN_SUBJECTS}
    for card in cards:
        if card["is_due"] and card["subject"] in counts:
            counts[card["subject"]] += 1
    return counts


def build_subject_score_presence(archive_text: str) -> Dict[str, bool]:
    if not archive_text:
        return {subject: False for subject in PLAN_SUBJECTS}
    presence = {subject: False for subject in PLAN_SUBJECTS}
    mock_rows = parse_mock_rows(archive_text)
    if mock_rows:
        for subject in SCORE_SUBJECTS:
            for row in mock_rows:
                if parse_score_cell(row[subject]) is not None:
                    presence[subject] = True
                    break
    for subject in ("数学一", "408"):
        if parse_subject_score_rows(archive_text, subject):
            presence[subject] = True
    return presence


def build_subject_progress_rows(
    archive_progress: Mapping[str, Mapping[str, object]],
    subject_logs: Mapping[str, int],
    subject_cards: Mapping[str, int],
    subject_due: Mapping[str, int],
    knowledge_maps: Mapping[str, Mapping[str, object]],
    score_presence: Mapping[str, bool],
    chapter_reports: Mapping[str, object],
) -> Tuple[List[Dict[str, object]], List[str], List[str]]:
    rows = []
    structured_subjects = []
    blank_subjects = []
    max_gap = 0.0
    for subject in SCORE_SUBJECTS:
        progress = archive_progress.get(subject, {})
        gap = progress.get("gap")
        if isinstance(gap, (int, float)):
            max_gap = max(max_gap, float(abs(gap)))

    for subject in SCORE_SUBJECTS:
        progress = archive_progress.get(subject, {})
        km = knowledge_maps.get(subject, {})
        row = {
            "subject": subject,
            "current": progress.get("current"),
            "target": progress.get("target"),
            "gap": progress.get("gap"),
            "judgement": progress.get("judgement", ""),
            "log_signal": subject_logs.get(subject, 0),
            "cards": subject_cards.get(subject, 0),
            "due_cards": subject_due.get(subject, 0),
            "knowledge_marked": km.get("marked_topics", 0),
            "knowledge_total": km.get("total_topics", 0),
            "has_score": bool(score_presence.get(subject)),
            "has_chapter_reports": bool(chapter_reports["reports"]) if subject == "408" else False,
        }
        row["structure_score"] = sum([
            1 if row["log_signal"] else 0,
            1 if row["cards"] else 0,
            1 if row["knowledge_marked"] else 0,
            1 if row["has_score"] else 0,
            1 if row["has_chapter_reports"] else 0,
        ])
        rows.append(row)
        if row["structure_score"]:
            structured_subjects.append(subject)
        else:
            blank_subjects.append(subject)

    for row in rows:
        gap_value = row["gap"]
        row["gap_ratio"] = 0.0
        if isinstance(gap_value, (int, float)) and max_gap > 0:
            row["gap_ratio"] = round(abs(float(gap_value)) / max_gap, 4)

    return rows, structured_subjects, blank_subjects


def build_review_payload(cards: Sequence[Mapping[str, object]]) -> Dict[str, object]:
    due_cards = [card for card in cards if card["is_due"]]
    by_subject = Counter(card["subject"] for card in due_cards)
    by_status = Counter(card["status"] for card in due_cards)
    overdue_buckets = Counter(card["overdue_bucket"] for card in due_cards)
    graduated_total = sum(1 for card in cards if card["graduated"])

    chapter_aggregate: Dict[Tuple[str, str], Dict[str, object]] = {}
    for card in cards:
        key = (card["subject"], card["chapter"])
        bucket = chapter_aggregate.setdefault(key, {
            "subject": card["subject"],
            "chapter": card["chapter"],
            "total_cards": 0,
            "due_cards": 0,
            "not_mastered_cards": 0,
        })
        bucket["total_cards"] += 1
        if card["is_due"]:
            bucket["due_cards"] += 1
        if card["status"] in {"不会", "半会"}:
            bucket["not_mastered_cards"] += 1

    top_chapters = sorted(
        chapter_aggregate.values(),
        key=lambda item: (item["due_cards"], item["not_mastered_cards"], item["total_cards"]),
        reverse=True,
    )[:6]

    return {
        "due_total": len(due_cards),
        "graduated_total": graduated_total,
        "by_subject": [{"label": subject, "value": by_subject.get(subject, 0)} for subject in PLAN_SUBJECTS],
        "by_status": [{"label": status, "value": by_status.get(status, 0)} for status in STATUS_ORDER],
        "overdue_buckets": [
            {"label": label, "value": overdue_buckets.get(label, 0)}
            for label in ("今天到期", "超期 1-3 天", "超期 4-7 天", "超期 8 天+")
        ],
        "top_chapters": top_chapters,
    }


def build_knowledge_payload(knowledge_maps: Mapping[str, Mapping[str, object]]) -> Dict[str, object]:
    rows = []
    totals = {"会": 0, "半会": 0, "不会": 0, "unmarked": 0, "total_topics": 0}
    for subject in PLAN_SUBJECTS:
        data = knowledge_maps.get(subject, {})
        row = {
            "subject": subject,
            "exists": bool(data.get("exists")),
            "total_topics": data.get("total_topics", 0),
            "会": data.get("会", 0),
            "半会": data.get("半会", 0),
            "不会": data.get("不会", 0),
            "unmarked": data.get("unmarked", 0),
            "marked_topics": data.get("marked_topics", 0),
        }
        row["marked_ratio"] = 0.0
        if row["total_topics"]:
            row["marked_ratio"] = round(row["marked_topics"] / row["total_topics"], 4)
        rows.append(row)
        for key in totals:
            totals[key] += row.get(key, 0)
    return {"by_subject": rows, "totals": totals}


def build_activity_payload(
    logs: Sequence[Mapping[str, object]],
    cards: Sequence[Mapping[str, object]],
    reports: Mapping[str, object],
    chapter_reports: Mapping[str, object],
    today: date,
) -> Dict[str, object]:
    log_dates = [entry["date"] for entry in logs]
    log_counts = Counter(log_dates)
    created_counts = Counter(parse_iso_date(card["created_at"]) for card in cards if parse_iso_date(card["created_at"]))
    reviewed_counts = Counter(parse_iso_date(card["last_review_at"]) for card in cards if parse_iso_date(card["last_review_at"]))

    latest_log = max(log_dates) if log_dates else None
    active_days_14 = sum(1 for day in set(log_dates) if today - timedelta(days=13) <= day <= today)
    recent_logs_30 = build_heatmap_series(log_counts, today, 30)
    card_created_30 = build_heatmap_series(created_counts, today, 30)
    card_reviewed_30 = build_heatmap_series(reviewed_counts, today, 30)

    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def within_period(day: Optional[date], start: date) -> bool:
        return day is not None and start <= day <= today

    recent_outputs = {
        "week": {
            "logs": sum(1 for day in log_dates if within_period(day, week_start)),
            "cards": sum(1 for card in cards if within_period(parse_iso_date(card["created_at"]), week_start)),
            "recaps": sum(1 for item in reports["recap_reports"] if within_period(item["date"], week_start)),
            "mock_reports": sum(1 for item in reports["mock_reports"] if within_period(item["date"], week_start)),
            "chapter_reports": sum(1 for item in chapter_reports["reports"] if within_period(parse_iso_date(item["date"]), week_start)),
        },
        "month": {
            "logs": sum(1 for day in log_dates if within_period(day, month_start)),
            "cards": sum(1 for card in cards if within_period(parse_iso_date(card["created_at"]), month_start)),
            "recaps": sum(1 for item in reports["recap_reports"] if within_period(item["date"], month_start)),
            "mock_reports": sum(1 for item in reports["mock_reports"] if within_period(item["date"], month_start)),
            "chapter_reports": sum(1 for item in chapter_reports["reports"] if within_period(parse_iso_date(item["date"]), month_start)),
        },
    }

    return {
        "latest_log_date": format_date(latest_log),
        "log_streak_days": compute_log_streak(log_dates),
        "active_days_14": active_days_14,
        "log_heatmap_30": recent_logs_30,
        "card_created_heatmap_30": card_created_30,
        "card_reviewed_heatmap_30": card_reviewed_30,
        "recent_outputs": recent_outputs,
    }


def build_quality_payload(
    archive_exists: bool,
    logs: Sequence[Mapping[str, object]],
    cards: Sequence[Mapping[str, object]],
    knowledge_maps: Mapping[str, Mapping[str, object]],
    reports: Mapping[str, object],
    chapter_reports: Mapping[str, object],
    score_presence: Mapping[str, bool],
    today: date,
) -> Dict[str, object]:
    subject_logs = build_subject_logs_signal(logs)
    subject_cards = build_subject_card_counts(cards)

    subject_matrix = []
    for subject in PLAN_SUBJECTS:
        km = knowledge_maps.get(subject, {})
        row = {
            "subject": subject,
            "logs": subject_logs.get(subject, 0) > 0,
            "wrong_cards": subject_cards.get(subject, 0) > 0,
            "knowledge_map": bool(km.get("exists")),
            "marked_topics": km.get("marked_topics", 0) > 0,
            "mock": bool(score_presence.get(subject)),
            "recap": reports["recap_subject_counts"].get(subject, 0) > 0,
            "chapter_report": bool(chapter_reports["reports"]) if subject == "408" else False,
        }
        subject_matrix.append(row)

    latest_log = max((entry["date"] for entry in logs), default=None)
    warnings: List[str] = []
    if not archive_exists:
        warnings.append("还没有学习者档案，驾驶舱会先展示空骨架。")
    if latest_log is None:
        warnings.append("还没有学习日志，连续性和时段活跃度暂时无法判断。")
    elif (today - latest_log).days >= 7:
        warnings.append(f"最近一次学习日志距今天已有 {(today - latest_log).days} 天，当前状态可能滞后。")
    if not reports["recap_reports"]:
        warnings.append("还没有周/月复盘报告，阶段性策略回看仍是空白。")
    if not reports["mock_reports"]:
        warnings.append("还没有模考分析报告，趋势判断暂时只能依赖档案和日志。")
    if sum(1 for card in cards if card["is_due"]) >= 10:
        warnings.append("到期复习已经形成积压，今天应先止损旧题。")
    for subject in PLAN_SUBJECTS:
        row = next(item for item in subject_matrix if item["subject"] == subject)
        if not row["wrong_cards"]:
            warnings.append(f"{subject} 还没有结构化错题卡，后续判断会偏粗。")
        if row["knowledge_map"] and not row["marked_topics"]:
            warnings.append(f"{subject} 的知识地图还没开始标注掌握度。")
    return {"warnings": warnings, "subject_matrix": subject_matrix}


def build_results_payload(cards: Sequence[Mapping[str, object]], chapter_reports: Mapping[str, object]) -> Dict[str, object]:
    total_cards = len(cards)
    promoted_cards = sum(1 for card in cards if card["promoted"])
    mastered_cards = sum(1 for card in cards if card["status"] == "会")
    covered_chapters = len({(card["subject"], card["chapter"]) for card in cards})
    covered_modules_408 = len({report["module"] for report in chapter_reports["reports"]})
    return {
        "total_cards": total_cards,
        "promoted_cards": promoted_cards,
        "mastered_cards": mastered_cards,
        "covered_chapters": covered_chapters,
        "covered_modules_408": covered_modules_408,
    }


def build_overview_payload(
    archive_basic: Mapping[str, object],
    logs: Sequence[Mapping[str, object]],
    cards: Sequence[Mapping[str, object]],
    reports: Mapping[str, object],
    activity: Mapping[str, object],
    structured_subjects: Sequence[str],
    today: date,
) -> Dict[str, object]:
    week_start = today - timedelta(days=today.weekday())
    new_cards_this_week = sum(1 for card in cards if parse_iso_date(card["created_at"]) and parse_iso_date(card["created_at"]) >= week_start)
    recap_count = len(reports["recap_reports"])
    mock_count = len(reports["mock_reports"])
    return {
        "today": today.isoformat(),
        "exam_date": archive_basic.get("exam_date", "-"),
        "days_until_exam": archive_basic.get("days_until_exam"),
        "latest_log_date": activity["latest_log_date"],
        "log_streak_days": activity["log_streak_days"],
        "active_days_14": activity["active_days_14"],
        "due_total": sum(1 for card in cards if card["is_due"]),
        "new_cards_this_week": new_cards_this_week,
        "reports_status": {
            "recap_count": recap_count,
            "mock_count": mock_count,
            "has_any": recap_count > 0 or mock_count > 0,
        },
        "total_cards": len(cards),
        "covered_subjects_count": len(structured_subjects),
        "stage": archive_basic.get("stage", ""),
    }


def build_overall_mock_trend(archive_text: str) -> Dict[str, object]:
    rows = parse_mock_rows(archive_text) if archive_text else []
    series = []
    for subject in SCORE_SUBJECTS:
        points = []
        for row in rows:
            score = parse_score_cell(row[subject])
            if score is None:
                continue
            note = row.get("备注", "") or "总模考"
            points.append({
                "date": row["date"],
                "paper": "总模考",
                "paper_type": "总模考",
                "paper_label": f"总模考 / {note}",
                "score": score,
            })
        series.append({
            "subject": subject,
            "color": SUBJECT_META[subject]["color"],
            "points": points,
        })
    total_points = []
    for row in rows:
        total_score = parse_score_cell(row["总分"])
        if total_score is None:
            continue
        note = row.get("备注", "") or "总模考"
        total_points.append({
            "exam_date": row["date"],
            "paper_type": "总模考",
            "paper": "总分",
            "paper_label": f"总模考 / {note}",
            "total_score": total_score,
            "issues": note,
            "note": note,
        })
    return {
        "series": series,
        "total_points": total_points,
        "has_data": any(item["points"] for item in series),
    }


def _empty_score_breakdown() -> Dict[str, None]:
    return {field: None for field in (
        "score_objective", "score_big", "loss_objective", "loss_big",
        "score_choice_ds", "score_choice_co", "score_choice_os", "score_choice_cn",
        "score_big_ds", "score_big_co", "score_big_os", "score_big_cn",
        "loss_choice_ds", "loss_choice_co", "loss_choice_os", "loss_choice_cn",
        "loss_big_ds", "loss_big_co", "loss_big_os", "loss_big_cn",
        "score_cloze", "score_reading", "score_new_type",
        "score_translation", "score_short_essay", "score_long_essay",
    )}


def build_legacy_subject_points(archive_text: str, subject: str) -> List[Dict[str, object]]:
    points = []
    if not archive_text:
        return points
    for row in parse_subject_score_rows(archive_text, subject):
        score = parse_score_cell(row["total"])
        if score is None:
            continue
        point = {
            "subject": subject,
            "exam_date": row["date"],
            "paper_type": row.get("paper_type", "模拟"),
            "paper": row["paper"],
            "paper_label": f"{row.get('paper_type', '模拟')} / {row['paper']}",
            "total_score": score,
            "issues": row.get("issues", ""),
            "note": row.get("note", ""),
            "source": "archive_summary",
        }
        point.update(_empty_score_breakdown())
        points.append(point)
    return points


def merge_score_points(
    detailed_records: Sequence[Mapping[str, object]],
    archive_text: str,
    subject: str,
) -> List[Dict[str, object]]:
    merged: Dict[Tuple[str, str, str], Dict[str, object]] = {}
    for record in build_legacy_subject_points(archive_text, subject):
        key = (record["exam_date"], record["paper_type"], record["paper"])
        merged[key] = dict(record)

    for record in detailed_records:
        if record["subject"] != subject:
            continue
        key = (str(record["exam_date"]), str(record["paper_type"]), str(record["paper"]))
        merged[key] = {
            "subject": subject,
            "exam_date": str(record["exam_date"]),
            "paper_type": str(record["paper_type"]),
            "paper": str(record["paper"]),
            "paper_label": f"{record['paper_type']} / {record['paper']}",
            "total_score": record["total_score"],
            "issues": str(record.get("issues", "")),
            "note": str(record.get("note", "")),
            "source": "record",
            **{field: record.get(field) for field in _empty_score_breakdown()},
        }

    rows = list(merged.values())
    rows.sort(key=lambda item: (item["exam_date"], item["paper_type"], item["paper"]))
    return rows


def filter_points_by_type(points: Sequence[Mapping[str, object]], paper_type: str) -> List[Dict[str, object]]:
    if paper_type == "all":
        return list(points)
    return [dict(point) for point in points if point["paper_type"] == paper_type]


def build_subject_score_trend(points: Sequence[Mapping[str, object]], subject: str) -> Dict[str, object]:
    latest = points[-1] if points else None
    recent_rows = []
    for point in sorted(points, key=lambda item: (item["exam_date"], item["paper_type"], item["paper"]), reverse=True)[:5]:
        row = {
            "date": point["exam_date"],
            "paper_type": point["paper_type"],
            "paper": point["paper"],
            "paper_label": point["paper_label"],
            "total_score": point["total_score"],
            "issues": point["issues"],
            "note": point["note"],
        }
        if subject == "数学一":
            row["score_objective"] = point.get("score_objective")
            row["score_big"] = point.get("score_big")
        elif subject == "408":
            row["main_weakness"] = top_weakness_from_408_record(point) or point["issues"]
        elif subject == "英语一":
            row["score_cloze"] = point.get("score_cloze")
            row["score_reading"] = point.get("score_reading")
            row["score_new_type"] = point.get("score_new_type")
            row["score_translation"] = point.get("score_translation")
            row["score_short_essay"] = point.get("score_short_essay")
            row["score_long_essay"] = point.get("score_long_essay")
        recent_rows.append(row)

    return {
        "points": list(points),
        "has_data": bool(points),
        "latest": latest,
        "filters": {
            "all": filter_points_by_type(points, "all"),
            "真题": filter_points_by_type(points, "真题"),
            "模拟": filter_points_by_type(points, "模拟"),
        },
        "recent_rows": recent_rows,
    }


def build_politics_points_from_overall(archive_text: str) -> List[Dict[str, object]]:
    """从「模考成绩追踪」综合表里抽政治分数,作为政治趋势的兜底数据源。

    issues/note 用 mock 行的备注,不再用 paper_label 顶替——空就让它空。
    """
    if not archive_text:
        return []
    points: List[Dict[str, object]] = []
    for row in parse_mock_rows(archive_text):
        score = parse_score_cell(row["政治"])
        if score is None:
            continue
        note = row.get("备注", "")
        paper_name = note or "总模考"
        points.append({
            "subject": "政治",
            "exam_date": row["date"],
            "paper_type": "总模考",
            "paper": paper_name,
            "paper_label": f"总模考 / {paper_name}",
            "total_score": score,
            "issues": "",
            "note": note,
            "source": "overall_mock",
        })
    return points


def build_score_trends_payload(obsidian_root: Path, archive_text: str) -> Dict[str, object]:
    detailed_records = collect_score_records(obsidian_root, ("数学一", "408", "英语一", "政治"))
    math_points = merge_score_points(detailed_records, archive_text, "数学一")
    cs_points = merge_score_points(detailed_records, archive_text, "408")
    english_points = merge_score_points(detailed_records, archive_text, "英语一")
    politics_points = merge_score_points(detailed_records, archive_text, "政治")
    overall = build_overall_mock_trend(archive_text)

    politics_fallback_used = False
    if not politics_points:
        politics_points = build_politics_points_from_overall(archive_text)
        politics_fallback_used = bool(politics_points)

    recent_records = []
    all_records = math_points + cs_points + english_points + politics_points
    for point in sorted(all_records, key=lambda item: (item["exam_date"], item["paper_type"], item["paper"]), reverse=True)[:5]:
        recent_records.append({
            "subject": point["subject"],
            "date": point["exam_date"],
            "paper_type": point["paper_type"],
            "paper": point["paper"],
            "total_score": point["total_score"],
            "paper_label": point["paper_label"],
        })

    return {
        "overall": overall,
        "total": build_subject_score_trend(overall["total_points"], "总分"),
        "math1": build_subject_score_trend(math_points, "数学一"),
        "408": {
            **build_subject_score_trend(cs_points, "408"),
            "has_loss_metrics": any(
                point.get(field) is not None
                for point in cs_points
                for field in (
                    "loss_choice_ds", "loss_choice_co", "loss_choice_os", "loss_choice_cn",
                    "loss_big_ds", "loss_big_co", "loss_big_os", "loss_big_cn",
                )
            ),
        },
        "english1": build_subject_score_trend(english_points, "英语一"),
        "politics": {
            **build_subject_score_trend(politics_points, "政治"),
            "fallback_used": politics_fallback_used,
        },
        "recent_records": recent_records,
    }


def build_payload(obsidian_root: Path, today: date) -> Dict[str, object]:
    archive_path, archive_text = safe_load_archive_text(obsidian_root)
    archive_exists = bool(archive_text)
    archive_basic = parse_archive_basic_info(archive_text, today) if archive_text else {
        "exam_date": "-",
        "days_until_exam": None,
        "latest_archive_update": "-",
        "stage": "",
        "focus_problems": [],
        "next_steps": [],
    }
    archive_progress = parse_archive_progress(archive_text) if archive_text else {}

    logs = collect_logs(obsidian_root)
    cards = collect_cards(obsidian_root, today)
    knowledge_maps = collect_knowledge_maps(obsidian_root)
    reports = collect_reports(obsidian_root)
    chapter_reports = collect_chapter_reports(obsidian_root)
    subject_logs = build_subject_logs_signal(logs)
    subject_cards = build_subject_card_counts(cards)
    subject_due = build_subject_due_counts(cards)
    score_presence = build_subject_score_presence(archive_text)
    subject_rows, structured_subjects, blank_subjects = build_subject_progress_rows(
        archive_progress,
        subject_logs,
        subject_cards,
        subject_due,
        knowledge_maps,
        score_presence,
        chapter_reports,
    )
    reviews = build_review_payload(cards)
    knowledge_payload = build_knowledge_payload(knowledge_maps)
    activity = build_activity_payload(logs, cards, reports, chapter_reports, today)
    score_trends = build_score_trends_payload(obsidian_root, archive_text)
    quality = build_quality_payload(
        archive_exists,
        logs,
        cards,
        knowledge_maps,
        reports,
        chapter_reports,
        score_presence,
        today,
    )
    results = build_results_payload(cards, chapter_reports)
    overview = build_overview_payload(archive_basic, logs, cards, reports, activity, structured_subjects, today)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "overview": overview,
        "subjects": {
            "progress": subject_rows,
            "structured_subjects": structured_subjects,
            "blank_subjects": blank_subjects,
        },
        "reviews": reviews,
        "score_trends": score_trends,
        "knowledge_maps": knowledge_payload,
        "activity": activity,
        "quality": quality,
        "results": results,
        "archive": {
            "exists": archive_exists,
            "path": str(archive_path),
            "focus_problems": archive_basic.get("focus_problems", []),
            "next_steps": archive_basic.get("next_steps", []),
            "latest_archive_update": archive_basic.get("latest_archive_update", "-"),
        },
    }
