#!/usr/bin/env python3
"""读取档案、最新日志、最新报告，生成稳定的 /load 上下文摘要。"""
import argparse
import calendar
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, TypedDict

from archive_ops import extract_list_items, load_archive_text, parse_daily_hours, parse_subject_targets
from constants import LOAD_COUNTDOWN_WINDOW_DAYS, LOAD_DUE_BACKLOG_WARNING_THRESHOLD
from env_util import resolve_obsidian_root
from study_ops import SCORE_SUBJECTS, count_due_reviews, parse_today


class LatestLogInfo(TypedDict):
    date: date
    path: str
    learned: List[str]
    blockers: List[str]
    review: List[str]


class LatestReportInfo(TypedDict):
    date: date
    path: str
    issues: List[str]
    next_actions: List[str]


def parse_exam_date(text: str) -> Optional[date]:
    match = re.search(r"考试日期\*\*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", text)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def parse_target_total(text: str) -> Optional[float]:
    match = re.search(r"当前目标总分\*\*[:：]\s*([0-9]+(?:\.[0-9]+)?)", text)
    return float(match.group(1)) if match else None


def parse_stage(text: str) -> str:
    match = re.search(r"当前阶段关键词\*\*[:：]\s*(.+)", text)
    if not match:
        return ""
    value = match.group(1).strip()
    if value.startswith("如「"):
        return ""
    return value


def parse_recent_update(text: str) -> Optional[date]:
    match = re.search(r"最近更新日期\*\*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", text)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def latest_log_info(obsidian_root: Path) -> Optional[LatestLogInfo]:
    log_dir = Path(obsidian_root) / "学习日志"
    latest_day: Optional[date] = None
    latest_path: Optional[Path] = None
    for log_path in log_dir.glob("*.md"):
        try:
            log_day = date.fromisoformat(log_path.stem)
        except ValueError:
            continue
        if latest_day is None or log_day > latest_day:
            latest_day = log_day
            latest_path = log_path
    if latest_day is None or latest_path is None:
        return None

    text = latest_path.read_text(encoding="utf-8")
    return {
        "date": latest_day,
        "path": str(latest_path),
        "learned": extract_list_items(text, "学到了什么"),
        "blockers": extract_list_items(text, "卡壳与挣扎"),
        "review": extract_list_items(text, "下次需要复习"),
    }


def parse_report_sort_date(filename: str) -> Optional[date]:
    mock_match = re.match(r"(\d{4}-\d{2}-\d{2})-模考分析\.md$", filename)
    if mock_match:
        return date.fromisoformat(mock_match.group(1))

    week_match = re.match(r"(\d{4})-W(\d{2})-周复盘\.md$", filename)
    if week_match:
        year = int(week_match.group(1))
        week = int(week_match.group(2))
        monday = date.fromisocalendar(year, week, 1)
        return monday + timedelta(days=6)

    month_match = re.match(r"(\d{4})-(\d{2})-月复盘\.md$", filename)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, last_day)

    return None


def latest_report_info(obsidian_root: Path) -> Optional[LatestReportInfo]:
    report_dir = Path(obsidian_root) / "复盘报告"
    latest_day: Optional[date] = None
    latest_path: Optional[Path] = None
    for report_path in report_dir.glob("*.md"):
        sort_day = parse_report_sort_date(report_path.name)
        if sort_day is None:
            continue
        if latest_day is None or sort_day > latest_day:
            latest_day = sort_day
            latest_path = report_path
    if latest_day is None or latest_path is None:
        return None

    text = latest_path.read_text(encoding="utf-8")
    issues = (
        extract_list_items(text, "关键问题")
        or extract_list_items(text, "本周卡点")
        or extract_list_items(text, "本月卡点")
    )
    next_actions = (
        extract_list_items(text, "下一步动作")
        or extract_list_items(text, "下周建议")
        or extract_list_items(text, "下月建议")
    )
    return {
        "date": latest_day,
        "path": str(latest_path),
        "issues": issues,
        "next_actions": next_actions,
    }


def unique_items(items: Sequence[str], limit: int) -> List[str]:
    result: List[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in result:
            continue
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def has_due_backlog(due_total: int) -> bool:
    return due_total >= LOAD_DUE_BACKLOG_WARNING_THRESHOLD


def should_show_countdown(days_until_exam: Optional[int]) -> bool:
    return days_until_exam is not None and 0 <= days_until_exam < LOAD_COUNTDOWN_WINDOW_DAYS


def build_priorities(
    focus_items: Sequence[str],
    latest_log: Optional[LatestLogInfo],
    latest_report: Optional[LatestReportInfo],
    due_total: int,
    due_counts: Dict[str, int],
) -> List[str]:
    candidates: List[str] = []
    candidates.extend(focus_items[:3])
    if latest_log:
        candidates.extend(latest_log["blockers"][:2])
    if latest_report:
        candidates.extend(latest_report["issues"][:2])
    if due_total:
        top_subject = max(SCORE_SUBJECTS, key=lambda subject: (due_counts.get(subject, 0), subject))
        candidates.append(f"{top_subject} 到期复习共 {due_total} 道，先防止旧题继续积压")
    return unique_items(candidates, 3)


def build_risks(
    latest_log: Optional[LatestLogInfo],
    latest_report: Optional[LatestReportInfo],
    due_total: int,
    today: date,
    exam_day: Optional[date],
) -> List[str]:
    risks: List[str] = []
    if has_due_backlog(due_total):
        risks.append(f"到期复习已积压 {due_total} 道，今天不先清旧题的话会继续滚大。")
    if latest_log and latest_log["blockers"]:
        risks.append(f"最近一次学习记录里最明显的卡点是：{latest_log['blockers'][0]}")
    if latest_report and latest_report["issues"]:
        risks.append(f"最近一次复盘/模考还在提示：{latest_report['issues'][0]}")
    if exam_day is not None:
        days_until = (exam_day - today).days
        if should_show_countdown(days_until):
            risks.append(f"距离考试只剩 {days_until} 天，计划和复盘要尽量收口，不适合再发散铺太多新坑。")
    return unique_items(risks, 3)


def build_first_step(
    archive_steps: Sequence[str],
    latest_report: Optional[LatestReportInfo],
    due_total: int,
    due_counts: Dict[str, int],
    latest_log: Optional[LatestLogInfo],
) -> str:
    if due_total:
        top_subject = max(SCORE_SUBJECTS, key=lambda subject: (due_counts.get(subject, 0), subject))
        return f"先用 20-30 分钟清掉 {top_subject} 最早到期的 3-5 道旧题，再进今天主线。"
    if archive_steps:
        return archive_steps[0]
    if latest_report and latest_report["next_actions"]:
        return latest_report["next_actions"][0]
    if latest_log and latest_log["review"]:
        return f"先回看：{latest_log['review'][0]}"
    return "先执行一次 `/plan_today`，把今天的第一块完整时间锁给最卡的那个科目。"


def build_warnings(
    today: date,
    exam_day: Optional[date],
    daily_hours: Optional[float],
    target_total: Optional[float],
    subject_targets: Dict[str, Optional[float]],
    latest_log: Optional[LatestLogInfo],
    latest_report: Optional[LatestReportInfo],
    due_total: int,
) -> List[str]:
    warnings: List[str] = []
    if exam_day is None:
        warnings.append("档案里还没有有效的考试日期，倒计时和阶段判断会偏弱。")
    if daily_hours is None:
        warnings.append("档案里还没有填写“每日可投入时长”，计划脚本会要求你显式传时长。")
    if target_total is None:
        warnings.append("档案里还没有填写目标总分，模考趋势只能看相对变化。")
    if any(subject_targets.get(subject) is None for subject in SCORE_SUBJECTS):
        warnings.append("各科目标分还没补全，模考分析会优先参考已填写科目。")
    if latest_log is None:
        warnings.append("还没有学习日志，/load 暂时只能基于档案本身给建议。")
    else:
        days_since_log = (today - latest_log["date"]).days
        if days_since_log > 7:
            warnings.append(f"最近一次学习日志已经是 {days_since_log} 天前，当前状态可能有滞后。")
    if latest_report is None:
        warnings.append("还没有复盘或模考报告，阶段风险主要来自档案和最近日志。")
    if has_due_backlog(due_total):
        warnings.append(f"到期复习积压 {due_total} 道，建议今天优先止损。")
    return warnings


def build_missing_fields(
    exam_day: Optional[date],
    daily_hours: Optional[float],
    target_total: Optional[float],
    subject_targets: Dict[str, Optional[float]],
) -> List[str]:
    missing: List[str] = []
    if exam_day is None:
        missing.append("考试日期")
    if daily_hours is None:
        missing.append("每日可投入时长")
    if target_total is None:
        missing.append("当前目标总分")
    for subject in SCORE_SUBJECTS:
        if subject_targets.get(subject) is None:
            missing.append(f"{subject}目标分")
    return missing


def build_stage_summary(
    stage: str,
    daily_hours: Optional[float],
    latest_log: Optional[LatestLogInfo],
    recent_update: Optional[date],
) -> str:
    segments: List[str] = []
    segments.append(stage or "当前阶段关键词还没明确写入档案")
    if daily_hours is not None:
        segments.append(f"日均可投入 {daily_hours:g} 小时")
    if latest_log:
        segments.append(f"最近一次学习记录在 {latest_log['date'].isoformat()}")
    elif recent_update:
        segments.append(f"档案最近更新在 {recent_update.isoformat()}")
    return "；".join(segments) + "。"


def build_markdown(
    today: date,
    stage_summary: str,
    days_until_exam: Optional[int],
    priorities: Sequence[str],
    risks: Sequence[str],
    first_step: str,
    warnings: Sequence[str],
    latest_log: Optional[LatestLogInfo],
    latest_report: Optional[LatestReportInfo],
) -> str:
    countdown_line = ""
    if should_show_countdown(days_until_exam):
        countdown_line = f"- **考试倒计时**：{days_until_exam} 天"

    lines = [
        f"# 备考上下文：{today.isoformat()}",
        "",
        "## 当前阶段",
        f"- {stage_summary}",
    ]
    if countdown_line:
        lines.append(countdown_line)

    lines.extend([
        "",
        "## 优先问题",
        *(f"{index}. {item}" for index, item in enumerate(priorities, start=1)),
        "",
        "## 风险提醒",
        *(f"- {item}" for item in risks),
        "",
        "## 立刻开始",
        f"- {first_step}",
        "",
        "## 数据来源",
        f"- 最近学习日志：{latest_log['date'].isoformat() if latest_log else '暂无'}",
        f"- 最近复盘/模考：{latest_report['path'] if latest_report else '暂无'}",
    ])
    if warnings:
        lines.extend([
            "",
            "## 缺口提醒",
            *(f"- {item}" for item in warnings),
        ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="加载 /load 所需上下文")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args()

    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    today = parse_today(args.today)
    archive_path, archive_text = load_archive_text(obsidian_root)

    exam_day = parse_exam_date(archive_text)
    daily_hours = parse_daily_hours(archive_text)
    target_total = parse_target_total(archive_text)
    stage = parse_stage(archive_text)
    recent_update = parse_recent_update(archive_text)
    focus_items = extract_list_items(archive_text, "最近聚焦问题（只保留 3-5 条）")
    archive_steps = extract_list_items(archive_text, "下一步建议（只保留 3 条）")
    subject_targets = parse_subject_targets(archive_text)
    latest_log = latest_log_info(obsidian_root)
    latest_report = latest_report_info(obsidian_root)
    due_total, due_counts = count_due_reviews(obsidian_root, today, SCORE_SUBJECTS)

    priorities = build_priorities(focus_items, latest_log, latest_report, due_total, due_counts)
    risks = build_risks(latest_log, latest_report, due_total, today, exam_day)
    if not risks:
        risks = ["当前没有突出的系统性风险，重点是把计划、复习和日志连续性保持住。"]
    first_step = build_first_step(archive_steps, latest_report, due_total, due_counts, latest_log)
    warnings = build_warnings(today, exam_day, daily_hours, target_total, subject_targets, latest_log, latest_report, due_total)
    missing_fields = build_missing_fields(exam_day, daily_hours, target_total, subject_targets)
    stage_summary = build_stage_summary(stage, daily_hours, latest_log, recent_update)
    days_until_exam = (exam_day - today).days if exam_day is not None else None

    print(json.dumps({
        "archive_path": str(archive_path),
        "today": today.isoformat(),
        "current_stage": stage_summary,
        "days_until_exam": days_until_exam,
        "show_countdown": should_show_countdown(days_until_exam),
        "priorities": priorities,
        "risks": risks,
        "first_step": first_step,
        "warnings": warnings,
        "missing_fields": missing_fields,
        "focus_problems": focus_items[:5],
        "due_total": due_total,
        "latest_log_path": latest_log["path"] if latest_log else None,
        "latest_report_path": latest_report["path"] if latest_report else None,
        "markdown": build_markdown(today, stage_summary, days_until_exam, priorities, risks, first_step, warnings, latest_log, latest_report),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
