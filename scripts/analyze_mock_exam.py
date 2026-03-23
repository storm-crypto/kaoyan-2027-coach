#!/usr/bin/env python3
"""记录模考成绩并生成分析报告。"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from archive_ops import (
    load_archive_text,
    load_template_markdown,
    parse_mock_rows,
    parse_score_cell,
    parse_subject_targets,
    upsert_mock_row,
)
from env_util import atomic_write, json_error, resolve_obsidian_root
from study_ops import SCORE_SUBJECTS
ALIASES = {"数学": "数学一", "英语": "英语一"}


def parse_score_args(tokens):
    scores = {}
    for token in tokens:
        if "=" not in token:
            json_error(f"成绩参数格式错误: {token}，应为 科目=分数")
        subject, raw_score = token.split("=", 1)
        subject = ALIASES.get(subject, subject)
        if subject not in SCORE_SUBJECTS:
            json_error(f"不支持的科目: {subject}")
        try:
            scores[subject] = float(raw_score)
        except ValueError:
            json_error(f"分数必须是数字: {token}")
    missing = [subject for subject in SCORE_SUBJECTS if subject not in scores]
    if missing:
        json_error(f"缺少科目成绩: {'、'.join(missing)}")
    return scores


def parse_args():
    raw_args = sys.argv[1:]
    obsidian_root_arg = None
    if raw_args and "=" not in raw_args[0] and not raw_args[0].startswith("--"):
        obsidian_root_arg = raw_args[0]
        raw_args = raw_args[1:]

    parser = argparse.ArgumentParser(description="分析模考成绩")
    parser.add_argument("scores", nargs="+", help="成绩参数，如 政治=62 数学一=118")
    parser.add_argument("--date", dest="exam_date", help="考试日期 YYYY-MM-DD")
    parser.add_argument("--note", default="", help="本次模考备注")
    args = parser.parse_args(raw_args)
    return obsidian_root_arg, args


def format_score(value):
    if value is None:
        return "-"
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f"{value:.1f}"


def format_delta(current, previous):
    if previous is None:
        return "首次记录"
    delta = current - previous
    if abs(delta) < 1e-9:
        return "持平"
    sign = "+" if delta > 0 else ""
    return f"{sign}{format_score(delta)}"


def target_judgement(score, target):
    if target is None:
        return "-", "待补目标"
    gap = score - target
    if gap >= 0:
        return f"+{format_score(gap)}", "达标"
    if gap >= -5:
        return format_score(gap), "接近目标"
    return format_score(gap), "偏弱"


def render_report(template, mapping):
    content = template
    for key, value in mapping.items():
        content = content.replace(f"{{{key}}}", value)
    return content + "\n"


def pick_action_subjects(scores, target_gaps):
    subjects = []
    for _, subject in sorted(target_gaps):
        if subject not in subjects:
            subjects.append(subject)
    for subject, _ in sorted(scores.items(), key=lambda item: (item[1], SCORE_SUBJECTS.index(item[0]))):
        if subject not in subjects:
            subjects.append(subject)
    return subjects[:2]


def main():
    obsidian_root_arg, args = parse_args()
    obsidian_root = resolve_obsidian_root(obsidian_root_arg)
    exam_day = date.fromisoformat(args.exam_date) if args.exam_date else date.today()
    scores = parse_score_args(args.scores)

    archive_path, archive_text = load_archive_text(obsidian_root)
    targets = parse_subject_targets(archive_text)
    previous_rows = parse_mock_rows(archive_text)
    previous_row = None
    for row in reversed(previous_rows):
        if row["date"] != exam_day.isoformat():
            previous_row = row
            break

    total_score = sum(scores[subject] for subject in SCORE_SUBJECTS)
    previous_total = parse_score_cell(previous_row["总分"]) if previous_row else None

    score_rows = []
    target_gaps = []
    for subject in SCORE_SUBJECTS:
        previous_score = parse_score_cell(previous_row[subject]) if previous_row else None
        target_score = targets.get(subject)
        target_delta, judgement = target_judgement(scores[subject], target_score)
        score_rows.append(
            f"| {subject} | {format_score(scores[subject])} | {format_score(previous_score)} | "
            f"{format_score(target_score)} | {target_delta} | {judgement} |"
        )
        if target_score is not None:
            target_gaps.append((scores[subject] - target_score, subject))

    all_targets_complete = all(targets.get(subject) is not None for subject in SCORE_SUBJECTS)
    target_total = sum(targets[subject] for subject in SCORE_SUBJECTS) if all_targets_complete else None
    if target_total:
        total_gap = total_score - target_total
        if total_gap >= 0:
            overall_judgement = f"总分达到当前目标线，领先 {format_score(total_gap)} 分。"
        else:
            overall_judgement = f"总分距离当前目标线还差 {format_score(abs(total_gap))} 分。"
    elif target_gaps:
        overall_judgement = "各科目标分尚未补全，先以已填写科目的差距和历次趋势来判断。"
    elif previous_total is not None:
        overall_judgement = f"总分较上次 {format_delta(total_score, previous_total)}。"
    else:
        overall_judgement = "已完成首次模考记录，后续重点看趋势。"

    issues = []
    for gap, subject in sorted(target_gaps)[:2]:
        if gap < 0:
            issues.append(f"{subject} 距目标还差 {format_score(abs(gap))} 分，需要优先补。")
    if previous_row:
        for subject in SCORE_SUBJECTS:
            previous_score = parse_score_cell(previous_row[subject])
            if previous_score is not None and scores[subject] < previous_score:
                issues.append(f"{subject} 比上次回落 {format_score(previous_score - scores[subject])} 分，建议回看最近训练策略。")
                break
    if not issues:
        issues.append("整体分数结构稳定，下一步重点转向把优势科目继续做厚。")

    action_subjects = pick_action_subjects(scores, target_gaps)
    next_actions = [
        f"优先复盘 {action_subjects[0]}：把这次失分点拆成 2-3 个可执行小专题。",
        f"给 {action_subjects[1]} 留一次计时训练，检验是知识漏洞还是节奏问题。",
        "三天内补一次短复盘，确认这次模考暴露的问题有没有被真正消化。",
    ]

    row = {
        "date": exam_day.isoformat(),
        "政治": format_score(scores["政治"]),
        "数学一": format_score(scores["数学一"]),
        "英语一": format_score(scores["英语一"]),
        "408": format_score(scores["408"]),
        "总分": format_score(total_score),
        "备注": args.note or "阶段模考",
    }
    atomic_write(archive_path, upsert_mock_row(archive_text, row))

    content = render_report(load_template_markdown("模考分析模板.md"), {
        "exam_date": exam_day.isoformat(),
        "score_rows": "\n".join(score_rows),
        "total_score": format_score(total_score),
        "total_delta": format_delta(total_score, previous_total),
        "overall_judgement": overall_judgement,
        "key_issues": "\n".join(f"- {item}" for item in issues[:3]),
        "next_actions": "\n".join(f"- {item}" for item in next_actions),
    })

    report_dir = Path(obsidian_root) / "复盘报告"
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = report_dir / f"{exam_day.isoformat()}-模考分析.md"
    atomic_write(output_path, content)

    print(json.dumps({
        "path": str(output_path),
        "archive": str(archive_path),
        "exam_date": exam_day.isoformat(),
        "total_score": round(total_score, 2),
        "total_delta": format_delta(total_score, previous_total),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
