#!/usr/bin/env python3
"""写入学习日志，并按需回写学习者档案。"""
import argparse
import json
import re
from datetime import date
from pathlib import Path

from archive_ops import load_archive_text
from env_util import atomic_write, json_error, resolve_obsidian_root


def parse_args():
    parser = argparse.ArgumentParser(description="记录今日学习进展")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--date", dest="log_date", help="日志日期 YYYY-MM-DD")
    parser.add_argument("--topic", required=True, help="今天学了什么的一句话概述")
    parser.add_argument("--hours", help="今日学习时长，如 3.5")
    parser.add_argument("--mode", default="综合学习", help="今日学习模式")
    parser.add_argument("--learned", action="append", default=[], help="今日掌握的知识点，可重复传入")
    parser.add_argument("--blocker", action="append", default=[], help="今日卡点，可重复传入")
    parser.add_argument("--mastered", action="append", default=[], help="已掌握知识点，格式：知识点|信心")
    parser.add_argument("--review", action="append", default=[], help="下次需要复习的内容，可重复传入")
    parser.add_argument(
        "--score",
        action="append",
        default=[],
        help="训练成绩，格式：科目|类型|来源|得分|满分|备注",
    )
    parser.add_argument("--coach-note", default="", help="教练评语")
    parser.add_argument("--weakness", action="append", default=[], help="回写短板雷达，格式：短板|科目|严重度|证据|当前状态|下一步")
    parser.add_argument("--error-pattern", action="append", default=[], help="回写高频错误模式，格式：错误模式|科目|出现频率|最近一次出现|备注")
    parser.add_argument("--archive-next-step", action="append", default=[], help="回写档案的下一步建议，可重复传入")
    return parser.parse_args()


def parse_date(value):
    return date.fromisoformat(value) if value else date.today()


def parse_row(value, expected_parts, label):
    parts = [part.strip() for part in value.split("|")]
    if len(parts) != expected_parts or any(part == "" for part in parts):
        json_error(f"{label} 参数格式错误，应为 {'|'.join(['字段'] * expected_parts)}")
    return parts


def parse_mastered(value):
    parts = [part.strip() for part in value.split("|", 1)]
    if len(parts) == 1:
        return parts[0], "中"
    if not parts[0] or not parts[1]:
        json_error("mastered 参数格式错误，应为 知识点|信心")
    return parts[0], parts[1]


def parse_score(value):
    parts = [part.strip() for part in value.split("|")]
    if len(parts) != 6 or any(part == "" for part in parts[:5]):
        json_error("score 参数格式错误，应为 科目|类型|来源|得分|满分|备注")

    try:
        score = float(parts[3])
        total = float(parts[4])
    except ValueError:
        json_error("score 参数中的得分和满分必须是数字")

    if total <= 0:
        json_error("score 参数中的满分必须大于 0")
    if score < 0:
        json_error("score 参数中的得分不能小于 0")

    return {
        "subject": parts[0],
        "kind": parts[1],
        "source": parts[2],
        "score": score,
        "total": total,
        "note": parts[5],
    }


def bullet_list(items, fallback):
    if not items:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in items)


def render_mastered(items):
    if not items:
        return "- 暂无明确记录"
    lines = []
    for item in items:
        topic, confidence = parse_mastered(item)
        lines.append(f"- {topic} - 信心：{confidence}")
    return "\n".join(lines)


def format_number(value):
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f"{value:.1f}"


def render_scores(items):
    if not items:
        return "- 今天没有单独记录训练成绩。"

    rows = [
        "| 科目 | 类型 | 来源 | 得分 | 满分 | 完成率 | 备注 |",
        "|------|------|------|------|------|--------|------|",
    ]
    for raw_item in items:
        item = parse_score(raw_item)
        rate = item["score"] / item["total"] * 100
        rows.append(
            "| {subject} | {kind} | {source} | {score} | {total} | {rate:.1f}% | {note} |".format(
                subject=item["subject"],
                kind=item["kind"],
                source=item["source"],
                score=format_number(item["score"]),
                total=format_number(item["total"]),
                rate=rate,
                note=item["note"] or "-",
            )
        )
    return "\n".join(rows)


def render_log_content(log_day, args):
    coach_note = args.coach_note or "今天有沉淀，明天继续围绕最卡的那 1 个点做收口。"
    hours = args.hours or "未记录"
    return "\n".join([
        f"# Session: {log_day.isoformat()}",
        "",
        "## 今日概览",
        f"- **主题**: {args.topic}",
        f"- **时长**: {hours}",
        f"- **模式**: {args.mode}",
        "",
        "## 学到了什么",
        bullet_list(args.learned, "今天的收获还比较散，建议明天补成更具体的知识点。"),
        "",
        "## 卡壳与挣扎",
        bullet_list(args.blocker, "今天没有显式记录卡点。"),
        "",
        "## 今日已掌握（含信心等级）",
        render_mastered(args.mastered),
        "",
        "## 训练成绩记录",
        render_scores(args.score),
        "",
        "## 下次需要复习",
        bullet_list(args.review, "暂未指定复习点，建议先回看今天最容易再次出错的内容。"),
        "",
        "## 教练评语",
        f"- {coach_note}",
        "",
    ])


def extract_section_body(text, heading):
    pattern = rf"(^## {re.escape(heading)}\n)(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, re.M | re.S)
    if not match:
        raise ValueError(f"档案中缺少区块：{heading}")
    return match.group(2)


def replace_section_body(text, heading, new_body):
    pattern = rf"(^## {re.escape(heading)}\n)(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, re.M | re.S)
    if not match:
        raise ValueError(f"档案中缺少区块：{heading}")
    prefix = text[:match.start(2)]
    suffix = text[match.end(2):]
    normalized_body = new_body.strip("\n") + "\n"
    if suffix.startswith("\n## "):
        return prefix + normalized_body + suffix
    return prefix + normalized_body + suffix.lstrip("\n")


def parse_table_rows(section_body, column_count):
    rows = []
    for line in section_body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
        if len(cells) != column_count:
            continue
        if set("".join(cells)) <= {"-", " "}:
            continue
        if any(cell in {"短板", "错误模式"} for cell in cells[:1]):
            continue
        rows.append(cells)
    return rows


def serialize_table(header, separator, rows, blank_columns):
    if not rows:
        rows = [[""] * blank_columns]
    return "\n".join([header, separator] + [f"| {' | '.join(row)} |" for row in rows])


def upsert_rows(existing_rows, new_rows, key_indexes):
    rows = [row for row in existing_rows if any(cell for cell in row)]
    for new_row in new_rows:
        replaced = False
        for index, row in enumerate(rows):
            if all(row[key] == new_row[key] for key in key_indexes):
                rows[index] = new_row
                replaced = True
                break
        if not replaced:
            rows.append(new_row)
    return rows


def update_archive_date(text, log_day):
    pattern = r"(- \*\*最近更新日期\*\*：)(.*)"
    if not re.search(pattern, text):
        return text
    return re.sub(pattern, rf"\g<1>{log_day.isoformat()}", text, count=1)


def update_archive(text, log_day, weaknesses, error_patterns, next_steps):
    updated_sections = []
    updated = update_archive_date(text, log_day)

    if weaknesses:
        rows = [parse_row(item, 6, "weakness") for item in weaknesses]
        existing = parse_table_rows(extract_section_body(updated, "短板雷达"), 6)
        merged = upsert_rows(existing, rows, key_indexes=(0, 1))
        updated = replace_section_body(
            updated,
            "短板雷达",
            serialize_table(
                "| 短板 | 科目 | 严重度 | 证据 | 当前状态 | 下一步 |",
                "|------|------|--------|------|----------|--------|",
                merged,
                6,
            ),
        )
        updated_sections.append("短板雷达")

    if error_patterns:
        rows = [parse_row(item, 5, "error-pattern") for item in error_patterns]
        existing = parse_table_rows(extract_section_body(updated, "高频错误模式统计"), 5)
        merged = upsert_rows(existing, rows, key_indexes=(0, 1))
        updated = replace_section_body(
            updated,
            "高频错误模式统计",
            serialize_table(
                "| 错误模式 | 科目 | 出现频率 | 最近一次出现 | 备注 |",
                "|----------|------|----------|--------------|------|",
                merged,
                5,
            ),
        )
        updated_sections.append("高频错误模式统计")

    if next_steps:
        numbered = "\n".join(f"{index}. {item}" for index, item in enumerate(next_steps[:3], start=1))
        updated = replace_section_body(updated, "下一步建议（只保留 3 条）", numbered)
        updated_sections.append("下一步建议")

    return updated, updated_sections


def main():
    args = parse_args()
    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    log_day = parse_date(args.log_date)

    log_dir = Path(obsidian_root) / "学习日志"
    log_dir.mkdir(parents=True, exist_ok=True)
    output_path = log_dir / f"{log_day.isoformat()}.md"
    atomic_write(output_path, render_log_content(log_day, args))

    updated_sections = []
    if args.weakness or args.error_pattern or args.archive_next_step:
        archive_path, archive_text = load_archive_text(obsidian_root)
        updated_archive, updated_sections = update_archive(
            archive_text,
            log_day,
            args.weakness,
            args.error_pattern,
            args.archive_next_step,
        )
        atomic_write(archive_path, updated_archive)

    print(json.dumps({
        "path": str(output_path),
        "date": log_day.isoformat(),
        "archive_updated": bool(updated_sections),
        "updated_sections": updated_sections,
        "score_count": len(args.score),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
