#!/usr/bin/env python3
"""创建新的错题追踪卡，并尽量完整保留题干与选项。

用法:
  python3 create_wrong_card.py [OBSIDIAN_ROOT] [科目]
      --chapter [章节]
      --topic [考点关键词]
      --source [来源]
      --question-id [qid-xxxxxxxxxxxx]
      --question [题干文本]
      [--options [多行选项文本]]
      [--option [单个选项]]
      [--error-tag 标签]
      [--wrong-reason 文本]
      [--solution 文本]
      [--pitfall 文本]
      [--point-judgment 文本]
      [--first-step 文本]
      [--formal-solution 文本]
      [--mistake-analysis 文本]
      [--next-time 文本]
      [--point-location 文本]
      [--breakthrough 文本]
      [--option-analysis 文本]
      [--dual-track 文本]
      [--trap 文本]
      [--knowledge-link 文本]
      [--memory-hook 文本]
      [--check-question 文本]
      [--comment 简评]
      [--today YYYY-MM-DD]

说明:
- 若未显式传入 --options/--option，会尝试从 --question 中自动拆出 A/B/C/D 等选项。
- 非选择题会在“### 选项（如有）”下写入“无”，保持卡片结构稳定。
"""
import argparse
import json
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import List, Sequence, Tuple

from constants import SRS_DEFAULT_EASE_FACTOR
from env_util import atomic_write, json_error, resolve_obsidian_root
from frontmatter import serialize_frontmatter
from study_ops import parse_today

QUESTION_ID_RE = re.compile(r"^qid-[0-9a-f]{12}$")
OPTION_LINE_RE = re.compile(r"^(?:[A-H][\.．、:：\)]|[（(][A-H][）\)]|正确\b|错误\b|True\b|False\b)", re.I)
INVALID_PATH_CHARS_RE = re.compile(r'[\\/:*?"<>|]+')
WHITESPACE_RE = re.compile(r"\s+")

SUBJECT_MAP = {
    "数学一": "数学一",
    "数学": "数学一",
    "408": "408",
    "政治": "政治",
    "英语一": "英语一",
    "英语": "英语一",
}

SUBJECT_TAGS = {
    "数学一": "math1",
    "408": "408",
    "政治": "politics",
    "英语一": "english1",
}


def parse_args() -> Tuple[Path, argparse.Namespace]:
    raw_args = sys.argv[1:]
    obsidian_root_arg = None
    if raw_args and raw_args[0] not in SUBJECT_MAP and not raw_args[0].startswith("--"):
        obsidian_root_arg = raw_args[0]
        raw_args = raw_args[1:]

    parser = argparse.ArgumentParser(description="创建新的错题追踪卡")
    parser.add_argument("subject", help="科目，如 数学一 / 408 / 政治 / 英语一")
    parser.add_argument("--chapter", required=True, help="章节/模块")
    parser.add_argument("--topic", required=True, help="考点关键词")
    parser.add_argument("--source", required=True, help="来源，如 900题 / 王道")
    parser.add_argument("--question-id", required=True, help="题卡主键 qid-xxxxxxxxxxxx")
    parser.add_argument("--question", required=True, help="题干文本；若包含选项且未显式传 options，会自动拆分")
    parser.add_argument("--options", default="", help="多行选项文本，可选")
    parser.add_argument("--option", action="append", default=[], help="单个选项，可重复传入")
    parser.add_argument("--error-tag", action="append", default=[], help="错因标签，可重复传入")
    parser.add_argument("--wrong-reason", default="", help="错误原因，可多行")
    parser.add_argument("--solution", default="", help="正确思路/核心结论，可多行")
    parser.add_argument("--pitfall", default="", help="易错点/变式提醒，可多行")
    parser.add_argument("--point-judgment", default="", help="数学详解：考点判断，可多行")
    parser.add_argument("--first-step", default="", help="数学详解：第一步怎么想到，可多行")
    parser.add_argument("--formal-solution", default="", help="数学详解：规范解法，可多行")
    parser.add_argument("--mistake-analysis", default="", help="数学详解：错因定位，可多行")
    parser.add_argument("--next-time", default="", help="数学详解：下次怎么做，可多行")
    parser.add_argument("--point-location", default="", help="408详解：考点定位，可多行")
    parser.add_argument("--breakthrough", default="", help="408详解：题干突破口，可多行")
    parser.add_argument("--option-analysis", default="", help="408详解：选项逐个辨析，可多行")
    parser.add_argument("--dual-track", default="", help="408详解：双轨解释，可多行")
    parser.add_argument("--trap", default="", help="408详解：干扰项陷阱，可多行")
    parser.add_argument("--knowledge-link", default="", help="408详解：知识网络串联，可多行")
    parser.add_argument("--memory-hook", default="", help="408详解：记忆钩子，可多行")
    parser.add_argument("--check-question", action="append", default=[], help="理解检查问题，可重复传入")
    parser.add_argument("--comment", default="首次归档", help="历史记录中的一句话简评")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args(raw_args)
    return resolve_obsidian_root(obsidian_root_arg), args


def split_nonempty_lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def normalize_subject(subject: str) -> str:
    normalized = SUBJECT_MAP.get(subject)
    if not normalized:
        json_error(f"未知科目 '{subject}'，支持: {', '.join(SUBJECT_MAP.keys())}")
    return normalized


def sanitize_path_segment(text: str) -> str:
    value = INVALID_PATH_CHARS_RE.sub("-", text.strip())
    value = WHITESPACE_RE.sub("", value)
    value = re.sub(r"-{2,}", "-", value).strip("-.")
    return value or "未命名"


def sanitize_tag_value(text: str) -> str:
    value = text.strip().lower()
    value = INVALID_PATH_CHARS_RE.sub("-", value)
    value = WHITESPACE_RE.sub("-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "unknown"


def merge_explicit_options(options_text: str, option_args: Sequence[str]) -> List[str]:
    lines = split_nonempty_lines(options_text)
    for item in option_args:
        lines.extend(split_nonempty_lines(item))
    return lines


def split_question_and_options(question_text: str, explicit_options: Sequence[str]) -> Tuple[List[str], List[str], str]:
    question_lines = split_nonempty_lines(question_text)
    if explicit_options:
        return question_lines, list(explicit_options), "explicit"

    first_option_index = None
    for index, line in enumerate(question_lines):
        if OPTION_LINE_RE.match(line):
            first_option_index = index
            break

    if first_option_index is None:
        return question_lines, [], "none"

    trailing_lines = question_lines[first_option_index:]
    option_like_count = sum(1 for line in trailing_lines if OPTION_LINE_RE.match(line))
    if option_like_count < 2:
        return question_lines, [], "none"

    return question_lines[:first_option_index], trailing_lines, "detected"


def render_bullet_block(lines: Sequence[str], fallback: str) -> str:
    items = list(lines) or [fallback]
    return "\n".join(f"- {line}" for line in items)


def render_numbered_block(lines: Sequence[str], fallback: str) -> str:
    items = list(lines) or [fallback]
    return "\n".join(f"{index}. {line}" for index, line in enumerate(items, start=1))


def merge_repeated_lines(values: Sequence[str]) -> List[str]:
    lines: List[str] = []
    for value in values:
        lines.extend(split_nonempty_lines(value))
    return lines


def build_math_detail_sections(args: argparse.Namespace) -> str:
    return (
        f"### 考点判断\n{render_bullet_block(split_nonempty_lines(args.point_judgment), '待补充')}\n\n"
        f"### 第一步怎么想到\n{render_bullet_block(split_nonempty_lines(args.first_step), '待补充')}\n\n"
        f"### 规范解法\n{render_bullet_block(split_nonempty_lines(args.formal_solution or args.solution), '待补充')}\n\n"
        f"### 错因定位\n{render_bullet_block(split_nonempty_lines(args.mistake_analysis or args.wrong_reason), '待补充')}\n\n"
        f"### 易错点\n{render_bullet_block(split_nonempty_lines(args.pitfall), '待补充')}\n\n"
        f"### 下次怎么做\n{render_bullet_block(split_nonempty_lines(args.next_time), '待补充')}\n\n"
        f"### 检查你是否真的懂了\n{render_numbered_block(merge_repeated_lines(args.check_question), '待补充')}\n"
    )


def build_408_detail_sections(args: argparse.Namespace) -> str:
    return (
        f"### 考点定位\n{render_bullet_block(split_nonempty_lines(args.point_location), '待补充')}\n\n"
        f"### 题干突破口\n{render_bullet_block(split_nonempty_lines(args.breakthrough), '待补充')}\n\n"
        f"### 选项逐个辨析\n{render_bullet_block(split_nonempty_lines(args.option_analysis or args.solution), '待补充')}\n\n"
        f"### 双轨解释\n{render_bullet_block(split_nonempty_lines(args.dual_track), '待补充')}\n\n"
        f"### 干扰项陷阱\n{render_bullet_block(split_nonempty_lines(args.trap or args.wrong_reason), '待补充')}\n\n"
        f"### 知识网络串联\n{render_bullet_block(split_nonempty_lines(args.knowledge_link), '待补充')}\n\n"
        f"### 记忆钩子\n{render_bullet_block(split_nonempty_lines(args.memory_hook or args.pitfall), '待补充')}\n\n"
        f"### 检查你是否真的懂了\n{render_numbered_block(merge_repeated_lines(args.check_question), '待补充')}\n"
    )


def build_generic_detail_sections(args: argparse.Namespace) -> str:
    return (
        f"### 错误原因\n{render_bullet_block(split_nonempty_lines(args.wrong_reason), '待补充')}\n\n"
        f"### 正确思路 / 核心结论\n{render_bullet_block(split_nonempty_lines(args.solution), '待补充')}\n\n"
        f"### 易错点 / 变式提醒\n{render_bullet_block(split_nonempty_lines(args.pitfall), '待补充')}\n"
    )


def build_detail_sections(subject: str, args: argparse.Namespace) -> str:
    if subject == "数学一":
        return build_math_detail_sections(args)
    if subject == "408":
        return build_408_detail_sections(args)
    return build_generic_detail_sections(args)


def build_card_body(
    subject: str,
    topic: str,
    source: str,
    question_id: str,
    question_lines: Sequence[str],
    option_lines: Sequence[str],
    args: argparse.Namespace,
    comment: str,
    today: str,
) -> str:
    topic_tag = sanitize_tag_value(topic)
    source_tag = sanitize_tag_value(source)
    subject_tag = SUBJECT_TAGS[subject]

    return (
        f"\n#subject/{subject_tag} #topic/{topic_tag} #status/不会 #source/{source_tag}\n\n"
        f"## {topic} — {source} — {question_id}\n\n"
        f"### 题目\n{render_bullet_block(question_lines, '待补题干')}\n\n"
        f"### 选项（如有）\n{render_bullet_block(option_lines, '无')}\n\n"
        f"{build_detail_sections(subject, args)}\n\n"
        f"### 历史记录\n- {today} - 不会 - {comment.strip() or '首次归档'}\n"
    )


def main() -> None:
    obsidian_root, args = parse_args()
    subject = normalize_subject(args.subject)
    if not QUESTION_ID_RE.match(args.question_id):
        json_error(f"question_id 格式非法: {args.question_id}")

    explicit_options = merge_explicit_options(args.options, args.option)
    question_lines, option_lines, options_source = split_question_and_options(args.question, explicit_options)
    if not question_lines:
        json_error("题干不能为空；如果题目里包含选项，请至少保留选项前的题干描述")

    today_obj = parse_today(args.today)
    today = today_obj.isoformat()
    next_review = (today_obj + timedelta(days=1)).isoformat()

    card_dir = (
        Path(obsidian_root)
        / "错题本"
        / subject
        / sanitize_path_segment(args.chapter)
    )
    card_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        f"{sanitize_path_segment(args.topic)}-"
        f"{sanitize_path_segment(args.source)}-"
        f"{args.question_id}.md"
    )
    output_path = card_dir / filename
    if output_path.exists():
        json_error(f"目标文件已存在: {output_path}")

    frontmatter = {
        "source": args.source.strip(),
        "question_id": args.question_id,
        "topic": args.topic.strip(),
        "error_tags": args.error_tag,
        "first_wrong_at": today,
        "last_review_at": today,
        "wrong_count": "1",
        "status": "不会",
        "next_review": next_review,
        "review_interval": "1",
        "ease_factor": f"{SRS_DEFAULT_EASE_FACTOR:.2f}",
    }
    key_order = [
        "source",
        "question_id",
        "topic",
        "error_tags",
        "first_wrong_at",
        "last_review_at",
        "wrong_count",
        "status",
        "next_review",
        "review_interval",
        "ease_factor",
    ]

    body = build_card_body(
        subject=subject,
        topic=args.topic.strip(),
        source=args.source.strip(),
        question_id=args.question_id,
        question_lines=question_lines,
        option_lines=option_lines,
        args=args,
        comment=args.comment,
        today=today,
    )
    atomic_write(output_path, serialize_frontmatter(frontmatter, key_order, body))

    print(json.dumps({
        "path": str(output_path),
        "subject": subject,
        "chapter": sanitize_path_segment(args.chapter),
        "topic": args.topic.strip(),
        "question_id": args.question_id,
        "question_line_count": len(question_lines),
        "option_count": len(option_lines),
        "options_source": options_source,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
