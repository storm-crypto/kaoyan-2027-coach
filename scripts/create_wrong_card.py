#!/usr/bin/env python3
"""创建新的错题追踪卡，并尽量完整保留题面原文。

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
      [--status 不会|半会|会]
      [--comment 简评]
      [--today YYYY-MM-DD]

说明:
- 题面统一只写入“### 题目”，不再单独生成“### 选项（如有）”区块。
- 若传入 --options/--option，会直接按原顺序拼接到题目正文末尾。
- 新建卡片时必须一次性传入完整解析；脚本会拒绝写出“待补充”占位符。
- 题干、选项与详解中的数学公式必须使用 $...$ 或 $$...$$ 包裹。
"""
import argparse
import json
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from constants import (
    SRS_DEFAULT_EASE_FACTOR,
    SRS_EASE_REWARD_STEP,
    SRS_GRADUATED_INTERVAL_DAYS,
    SRS_HALF_KNOWN_INTERVAL_MULTIPLIER,
)
from env_util import atomic_write, json_error, resolve_obsidian_root, sanitize_path_segment
from frontmatter import serialize_frontmatter
from study_ops import parse_today
from wrong_card_path_map import resolve_wrong_card_chapter

QUESTION_ID_RE = re.compile(r"^qid-[0-9a-f]{12}$")
INVALID_PATH_CHARS_RE = re.compile(r'[\\/:*?"<>|]+')
WHITESPACE_RE = re.compile(r"\s+")
LATEX_SEGMENT_RE = re.compile(r"\$\$.*?\$\$|\$(?!\$).*?(?<!\$)\$", re.S)
DISPLAY_MATH_SEGMENT_RE = re.compile(r"\$\$.*?\$\$", re.S)
INLINE_MATH_SEGMENT_RE = re.compile(r"\$[^$]+\$")
DISPLAY_BLOCK_DELIM = "$$"
TAG_VALUE_MAX_LENGTH = 32
PLACEHOLDER_TOKENS = ("待补充", "待补题干")
UNWRAPPED_MATH_PATTERNS = (
    re.compile(
        r"\\(?:frac|dfrac|tfrac|sqrt|sum|prod|int|lim|sin|cos|tan|cot|sec|csc|ln|log|exp|"
        r"cdot|times|leq|geq|neq|infty|left|right|mathrm|text)\b"
    ),
    re.compile(r"[A-Za-z0-9\)\]]\s*(?:\^|_)\s*[{(]?[A-Za-z0-9+-]"),
    re.compile(r"[A-Za-z](?:['′]{0,2})?\([^)\n]+\)\s*(?:[<>]=?|=|≤|≥|≠)\s*[-+*/()A-Za-z0-9]"),
    re.compile(r"(?<![A-Za-z])[A-Za-z](?:['′]{0,2})?\s*(?:[<>]=?|=|≤|≥|≠)\s*[-+*/()A-Za-z0-9]"),
)

# 排版可读性硬约束：单条详解行的散文长度上限（LaTeX 不计），以及规范解法单行散文上限。
# 长度衡量的是“散文密度”，公式先被 strip 掉，避免合法的长块公式被误判为拥挤。
MAX_DETAIL_LINE_LENGTH = 120
MAX_SINGLE_LINE_FORMAL_SOLUTION_LENGTH = 80
# 规范解法挤成一行时的「行内公式墙」阈值：散文 strip 掉 LaTeX 后量不出来，
# 所以另按「一行里连排多少段行内 $...$」和「单行 raw 字数」来兜。
MAX_FORMAL_INLINE_SEGMENTS_PER_LINE = 3
MAX_SINGLE_LINE_FORMAL_RAW_LENGTH = 140
# 考点判断/考点定位 里若把多个字段塞进同一行，就属于拥挤；这些是结构化字段标签。
STRUCTURED_POINT_LABELS = ("题型", "章节", "考点", "难度", "考频", "突破口")

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
    if (
        raw_args
        and raw_args[0] not in SUBJECT_MAP
        and not raw_args[0].startswith("--")
        and looks_like_obsidian_root_arg(raw_args[0])
    ):
        obsidian_root_arg = raw_args[0]
        raw_args = raw_args[1:]

    parser = argparse.ArgumentParser(description="创建新的错题追踪卡")
    parser.add_argument("subject", help="科目，如 数学一 / 408 / 政治 / 英语一")
    parser.add_argument("--chapter", required=True, help="章节/模块")
    parser.add_argument("--topic", required=True, help="考点关键词")
    parser.add_argument("--source", required=True, help="来源，如 900题 / 王道")
    parser.add_argument("--question-id", required=True, help="题卡主键 qid-xxxxxxxxxxxx")
    parser.add_argument("--question", required=True, help="题面原文；如有选项，建议直接一起传入")
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
    parser.add_argument(
        "--check-question",
        action="append",
        default=[],
        help="理解检查问题（数学一/408 通用），可重复传入",
    )
    parser.add_argument(
        "--status",
        default="不会",
        choices=["不会", "半会", "会"],
        help="新建卡片时的初始掌握状态，默认 不会",
    )
    parser.add_argument("--comment", default="首次归档", help="历史记录中的一句话简评")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args(raw_args)
    return resolve_obsidian_root(obsidian_root_arg), args


def split_nonempty_lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def looks_like_obsidian_root_arg(token: str) -> bool:
    candidate = Path(token).expanduser()
    return (
        candidate.exists()
        or candidate.is_absolute()
        or token in {".", ".."}
        or token.startswith(("~/", "./", "../"))
        or "/" in token
        or "\\" in token
    )


def normalize_subject(subject: str) -> str:
    normalized = SUBJECT_MAP.get(subject)
    if not normalized:
        json_error(f"未知科目 '{subject}'，支持: {', '.join(SUBJECT_MAP.keys())}")
    return normalized


def sanitize_tag_value(text: str) -> str:
    value = text.strip().lower()
    value = INVALID_PATH_CHARS_RE.sub("-", value)
    value = WHITESPACE_RE.sub("-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    if len(value) > TAG_VALUE_MAX_LENGTH:
        truncated = value[:TAG_VALUE_MAX_LENGTH].rstrip("-")
        if "-" in truncated:
            truncated = truncated.rsplit("-", 1)[0]
        value = truncated or value[:TAG_VALUE_MAX_LENGTH].strip("-")
    return value or "unknown"


def merge_explicit_options(options_text: str, option_args: Sequence[str]) -> List[str]:
    lines = split_nonempty_lines(options_text)
    for item in option_args:
        lines.extend(split_nonempty_lines(item))
    return lines


def detect_duplicate_options(question_text: str, explicit_options: Sequence[str]) -> List[str]:
    """检测 --question 是否已包含与 --option/--options 完全相同的选项行。

    返回重复出现的选项列表（按字面 strip 后比较）。空表示无冲突。
    调用方应在拼接前检查并 fail fast，避免双传导致选项在 ### 题目 区块重复落盘。
    """
    if not explicit_options:
        return []
    question_lines = split_nonempty_lines(question_text)
    question_set = {line.strip() for line in question_lines if line.strip()}
    explicit_set = {opt.strip() for opt in explicit_options if opt.strip()}
    return sorted(question_set & explicit_set)


def build_question_lines(question_text: str, explicit_options: Sequence[str]) -> Tuple[List[str], str]:
    question_lines = split_nonempty_lines(question_text)
    if explicit_options:
        question_lines = [*question_lines, *explicit_options]
        return question_lines, "explicit"
    return question_lines, "none"


def render_bullet_block(lines: Sequence[str], fallback: str) -> str:
    items = list(lines) or [fallback]
    return "\n".join(f"- {line}" for line in items)


def render_markdown_block(text: str, fallback: str) -> str:
    """把规范解法规整成「疏朗」版式：块单元之间留恰好一个空行。

    块单元 = 一段 `$$...$$` 块公式（可跨多行，内部保持单 `\\n` 连续，MathJax/Obsidian
    才认 display），或块外一行非空文字。模型传入的空行先统一丢弃，再在单元之间重新
    插入恰好一个空行——这样无论模型写得紧还是松，落盘都是同一套可扫读版式，且 `$$`
    块前后必有空行。否则 Obsidian 会把步骤行和块公式挤成一坨、`$$` 也得不到 display 间距。

    单行 `$$...$$`（定界与公式同一行）当普通文字单元原样保留。`$$` 不成对（块未闭合）
    时保守降级：按原非空行单 `\\n` 拼接，绝不臆造闭合或丢内容。空内容才回退占位。
    """
    units: List[str] = []
    block_buf: List[str] = []
    in_block = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped == DISPLAY_BLOCK_DELIM:
            if in_block:
                block_buf.append(DISPLAY_BLOCK_DELIM)
                units.append("\n".join(block_buf))
                block_buf = []
                in_block = False
            else:
                block_buf = [DISPLAY_BLOCK_DELIM]
                in_block = True
            continue
        if in_block:
            if stripped:
                block_buf.append(stripped)
            continue
        if stripped:
            units.append(stripped)
    if in_block:  # `$$` 未闭合：放弃疏朗重排，保守拼接，不损坏内容
        lines = split_nonempty_lines(text)
        return "\n".join(lines) if lines else f"- {fallback}"
    if not units:
        return f"- {fallback}"
    return "\n\n".join(units)


def render_numbered_block(lines: Sequence[str], fallback: str) -> str:
    items = list(lines) or [fallback]
    return "\n".join(f"{index}. {line}" for index, line in enumerate(items, start=1))


def merge_repeated_lines(values: Sequence[str]) -> List[str]:
    lines: List[str] = []
    for value in values:
        lines.extend(split_nonempty_lines(value))
    return lines


def has_nonempty_text(value: str) -> bool:
    return bool(split_nonempty_lines(value))


def has_nonempty_values(values: Sequence[str]) -> bool:
    return bool(merge_repeated_lines(values))


def validate_chapter_argument(chapter: str) -> None:
    normalized = chapter.strip()
    if "/" in normalized or "\\" in normalized:
        json_error(
            "--chapter 应传章节键而不是目录路径，例如传“数列极限”，不要传“高等数学/01 第一章 函数、极限、连续/03 第三节 数列极限”"
        )


def validate_required_detail_fields(subject: str, args: argparse.Namespace) -> None:
    if subject == "数学一":
        checks = [
            ("--point-judgment", has_nonempty_text(args.point_judgment)),
            ("--first-step", has_nonempty_text(args.first_step)),
            ("--formal-solution", has_nonempty_text(args.formal_solution)),
            ("--mistake-analysis", has_nonempty_text(args.mistake_analysis)),
            ("--pitfall", has_nonempty_text(args.pitfall)),
            ("--next-time", has_nonempty_text(args.next_time)),
            ("--check-question（至少 1 条）", has_nonempty_values(args.check_question)),
        ]
    elif subject == "408":
        checks = [
            ("--point-location", has_nonempty_text(args.point_location)),
            ("--breakthrough", has_nonempty_text(args.breakthrough)),
            ("--option-analysis", has_nonempty_text(args.option_analysis)),
            ("--dual-track", has_nonempty_text(args.dual_track)),
            ("--trap", has_nonempty_text(args.trap)),
            ("--knowledge-link", has_nonempty_text(args.knowledge_link)),
            ("--memory-hook", has_nonempty_text(args.memory_hook)),
            ("--check-question（至少 1 条）", has_nonempty_values(args.check_question)),
        ]
    else:
        checks = [
            ("--wrong-reason", has_nonempty_text(args.wrong_reason)),
            ("--solution", has_nonempty_text(args.solution)),
            ("--pitfall", has_nonempty_text(args.pitfall)),
        ]

    missing_fields = [label for label, ok in checks if not ok]
    if missing_fields:
        json_error(
            f"{subject} 新建错题卡时必须一次性传入完整解析，缺少: {', '.join(missing_fields)}"
        )


def strip_latex_segments(text: str) -> str:
    return LATEX_SEGMENT_RE.sub(" ", text)


def has_inline_display_math_text(text: str) -> Optional[str]:
    for original_line in split_nonempty_lines(text):
        # 只拦“同一行里 $$...$$ 块公式与文字混排”；裸 $$ 定界行（多行块公式的开/合）放过。
        if not DISPLAY_MATH_SEGMENT_RE.search(original_line):
            continue
        stripped_line = DISPLAY_MATH_SEGMENT_RE.sub(" ", original_line).strip()
        if stripped_line:
            return original_line.strip()
    return None


def find_unwrapped_math_excerpt(text: str) -> Optional[str]:
    # 先整体抹掉 $$...$$ 块公式（含跨行，DISPLAY_MATH_SEGMENT_RE 带 re.S），
    # 这样多行块公式内部的 \int、上下标等不会被误判成“未包裹的裸公式”。
    scrubbed = DISPLAY_MATH_SEGMENT_RE.sub(" ", text)
    for original_line in split_nonempty_lines(scrubbed):
        stripped_line = strip_latex_segments(original_line)
        for pattern in UNWRAPPED_MATH_PATTERNS:
            if pattern.search(stripped_line):
                return original_line.strip()
    return None


def validate_latex_wrapping(args: argparse.Namespace, explicit_options: Sequence[str]) -> None:
    field_values = [
        ("--question", [args.question]),
        ("--option", explicit_options),
        ("--wrong-reason", [args.wrong_reason]),
        ("--solution", [args.solution]),
        ("--pitfall", [args.pitfall]),
        ("--point-judgment", [args.point_judgment]),
        ("--first-step", [args.first_step]),
        ("--formal-solution", [args.formal_solution]),
        ("--mistake-analysis", [args.mistake_analysis]),
        ("--next-time", [args.next_time]),
        ("--point-location", [args.point_location]),
        ("--breakthrough", [args.breakthrough]),
        ("--option-analysis", [args.option_analysis]),
        ("--dual-track", [args.dual_track]),
        ("--trap", [args.trap]),
        ("--knowledge-link", [args.knowledge_link]),
        ("--memory-hook", [args.memory_hook]),
        ("--check-question", list(args.check_question)),
    ]
    violations = []
    style_violations = []
    for field_name, values in field_values:
        for value in values:
            if not value or not value.strip():
                continue
            excerpt = find_unwrapped_math_excerpt(value)
            if excerpt:
                violations.append(f"{field_name}: {excerpt}")
            if len(violations) >= 3:
                break
            style_excerpt = has_inline_display_math_text(value)
            if style_excerpt:
                style_violations.append(f"{field_name}: {style_excerpt}")
            if len(style_violations) >= 3:
                break
        if len(violations) >= 3:
            break
        if len(style_violations) >= 3:
            break

    if violations:
        json_error(
            "检测到疑似未用 $...$ 包裹的数学公式，请改成 LaTeX 后重试："
            + "；".join(violations)
        )
    if style_violations:
        json_error(
            "检测到把 $$...$$ 块公式嵌进了解释句中，请把句中短公式改成 $...$，块公式单独成行："
            + "；".join(style_violations)
        )


def visual_len(text: str) -> int:
    """衡量一行的“散文长度”：先去掉 LaTeX 片段再数字符。

    长块公式（`\\frac`、`\\int`、反斜杠、花括号都算字符）不应被当成“拥挤”，
    真正要拦的是把多个判断/字段塞进同一行的长散文。所以统一按 strip 掉公式
    后的可读文本长度来量。
    """
    return len(strip_latex_segments(text).strip())


def count_inline_math_segments(line: str) -> int:
    """数一行里有多少段行内 `$...$`（先抹掉 `$$...$$` 块，避免误算块公式里的 `$`）。

    用于识别「行内公式墙」：把整段推导写成一行连排的 `$...$`，散文密度量不出来，
    但段数能暴露它该被拆成多步、关键变形该用独立块公式。
    """
    scrubbed = DISPLAY_MATH_SEGMENT_RE.sub(" ", line)
    return len(INLINE_MATH_SEGMENT_RE.findall(scrubbed))


def count_structured_labels(line: str) -> int:
    """统计一行里出现了多少个结构化字段标签（题型：/章节：/...）。

    半角冒号先归一化成全角，避免 `题型:` 这种写法漏检。
    """
    normalized = line.replace(":", "：")
    return sum(1 for label in STRUCTURED_POINT_LABELS if f"{label}：" in normalized)


def find_overlong_detail_line(field_name: str, text: str) -> Optional[str]:
    for line in split_nonempty_lines(text):
        if visual_len(line) > MAX_DETAIL_LINE_LENGTH:
            return f"{field_name}: {line}"
    return None


def find_crammed_label_line(text: str) -> Optional[str]:
    for line in split_nonempty_lines(text):
        if count_structured_labels(line) >= 2:
            return line
    return None


def validate_readable_layout(subject: str, args: argparse.Namespace) -> None:
    """排版可读性硬约束：拒绝拥挤详解，让错题卡保持可复习。

    1. 任意详解行散文超过 MAX_DETAIL_LINE_LENGTH（LaTeX 不计）→ 拒绝落盘。
    2. 考点判断/考点定位 把 ≥2 个结构化字段塞进同一行 → 拒绝落盘。
    3. 规范解法只有一行且散文超过 MAX_SINGLE_LINE_FORMAL_SOLUTION_LENGTH
       → 拒绝落盘，提示拆成步骤。
    题面原文（--question）和选项不参与本校验，允许保留长原文。
    """
    if subject == "数学一":
        detail_fields = [
            ("--point-judgment", args.point_judgment),
            ("--first-step", args.first_step),
            ("--formal-solution", args.formal_solution),
            ("--mistake-analysis", args.mistake_analysis),
            ("--pitfall", args.pitfall),
            ("--next-time", args.next_time),
        ] + [("--check-question", q) for q in args.check_question]
        label_fields = [("--point-judgment", args.point_judgment)]
    elif subject == "408":
        detail_fields = [
            ("--point-location", args.point_location),
            ("--breakthrough", args.breakthrough),
            ("--option-analysis", args.option_analysis),
            ("--dual-track", args.dual_track),
            ("--trap", args.trap),
            ("--knowledge-link", args.knowledge_link),
            ("--memory-hook", args.memory_hook),
        ] + [("--check-question", q) for q in args.check_question]
        label_fields = [("--point-location", args.point_location)]
    else:
        detail_fields = [
            ("--wrong-reason", args.wrong_reason),
            ("--solution", args.solution),
            ("--pitfall", args.pitfall),
        ]
        label_fields = []

    overlong = []
    for field_name, text in detail_fields:
        if not text or not text.strip():
            continue
        excerpt = find_overlong_detail_line(field_name, text)
        if excerpt:
            overlong.append(excerpt)
        if len(overlong) >= 3:
            break
    if overlong:
        json_error(
            f"详解排版过密：以下行散文超过 {MAX_DETAIL_LINE_LENGTH} 字（LaTeX 不计），"
            "请拆成多条，每条只写一个判断/动作：" + "；".join(overlong)
        )

    for field_name, text in label_fields:
        if not text or not text.strip():
            continue
        crammed = find_crammed_label_line(text)
        if crammed:
            json_error(
                f"详解排版过密：{field_name} 同一行包含多个字段。请拆成多行：\n"
                "题型：...\n章节：...\n考点：...\n难度：...\n考频：...\n突破口：...\n"
                f"问题行：{crammed}"
            )

    if subject == "数学一":
        formal_lines = split_nonempty_lines(args.formal_solution)
        if len(formal_lines) == 1:
            line = formal_lines[0]
            prose_wall = visual_len(line) > MAX_SINGLE_LINE_FORMAL_SOLUTION_LENGTH
            # 行内公式墙：整行没有独立块公式，却把多段行内 $...$ 连排成一长行
            # （或单段巨型行内公式）。散文密度量不出来，靠段数 / raw 长度兜。
            inline_wall = DISPLAY_MATH_SEGMENT_RE.search(line) is None and (
                count_inline_math_segments(line) >= MAX_FORMAL_INLINE_SEGMENTS_PER_LINE
                or len(line) > MAX_SINGLE_LINE_FORMAL_RAW_LENGTH
            )
            if prose_wall or inline_wall:
                json_error(
                    "规范解法排版过密：--formal-solution 挤成一行。请拆成多步——"
                    "每步单独成行，关键变形/最终结论用独立成行的块公式 $$...$$，"
                    "不要把整段推导写成一行连排的行内 $...$。"
                )


def ensure_no_placeholder_tokens(card_text: str) -> None:
    remaining = [token for token in PLACEHOLDER_TOKENS if token in card_text]
    if remaining:
        json_error(f"卡片仍包含未落盘占位符: {', '.join(remaining)}")


def build_math_detail_sections(args: argparse.Namespace) -> str:
    return (
        f"### 考点判断\n{render_bullet_block(split_nonempty_lines(args.point_judgment), '待补充')}\n\n"
        f"### 第一步怎么想到\n{render_bullet_block(split_nonempty_lines(args.first_step), '待补充')}\n\n"
        f"### 规范解法\n{render_markdown_block(args.formal_solution, '待补充')}\n\n"
        f"### 错因定位\n{render_bullet_block(split_nonempty_lines(args.mistake_analysis), '待补充')}\n\n"
        f"### 易错点\n{render_bullet_block(split_nonempty_lines(args.pitfall), '待补充')}\n\n"
        f"### 下次怎么做\n{render_bullet_block(split_nonempty_lines(args.next_time), '待补充')}\n\n"
        f"### 检查你是否真的懂了\n{render_numbered_block(merge_repeated_lines(args.check_question), '待补充')}\n"
    )


def build_408_detail_sections(args: argparse.Namespace) -> str:
    return (
        f"### 考点定位\n{render_bullet_block(split_nonempty_lines(args.point_location), '待补充')}\n\n"
        f"### 题干突破口\n{render_bullet_block(split_nonempty_lines(args.breakthrough), '待补充')}\n\n"
        f"### 选项逐个辨析\n{render_bullet_block(split_nonempty_lines(args.option_analysis), '待补充')}\n\n"
        f"### 双轨解释\n{render_bullet_block(split_nonempty_lines(args.dual_track), '待补充')}\n\n"
        f"### 干扰项陷阱\n{render_bullet_block(split_nonempty_lines(args.trap), '待补充')}\n\n"
        f"### 知识网络串联\n{render_bullet_block(split_nonempty_lines(args.knowledge_link), '待补充')}\n\n"
        f"### 记忆钩子\n{render_bullet_block(split_nonempty_lines(args.memory_hook), '待补充')}\n\n"
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


def compute_initial_review_schedule(status: str) -> Tuple[int, float]:
    if status == "不会":
        return 1, SRS_DEFAULT_EASE_FACTOR
    if status == "半会":
        return max(int(1 * SRS_HALF_KNOWN_INTERVAL_MULTIPLIER), 2), SRS_DEFAULT_EASE_FACTOR
    return min(max(int(1 * SRS_DEFAULT_EASE_FACTOR), 1), SRS_GRADUATED_INTERVAL_DAYS), (
        SRS_DEFAULT_EASE_FACTOR + SRS_EASE_REWARD_STEP
    )


def build_card_body(
    subject: str,
    topic: str,
    source: str,
    question_id: str,
    question_lines: Sequence[str],
    detail_sections: str,
    status: str,
    comment: str,
    today: str,
) -> str:
    topic_tag = sanitize_tag_value(topic)
    source_tag = sanitize_tag_value(source)
    subject_tag = SUBJECT_TAGS[subject]

    return (
        f"\n#subject/{subject_tag} #topic/{topic_tag} #status/{status} #source/{source_tag}\n\n"
        f"## {topic} — {source} — {question_id}\n\n"
        f"### 题目\n{render_bullet_block(question_lines, '待补题干')}\n\n"
        f"{detail_sections}\n\n"
        f"### 历史记录\n- {today} - {status} - {comment.strip() or '首次归档'}\n"
    )


def main() -> None:
    obsidian_root, args = parse_args()
    subject = normalize_subject(args.subject)
    validate_chapter_argument(args.chapter)
    if not QUESTION_ID_RE.match(args.question_id):
        json_error(f"question_id 格式非法: {args.question_id}")

    explicit_options = merge_explicit_options(args.options, args.option)
    duplicates = detect_duplicate_options(args.question, explicit_options)
    if duplicates:
        listing = "\n".join(f"  - {item}" for item in duplicates)
        json_error(
            "题面与显式选项重复：以下选项同时出现在 --question 和 --option/--options 中：\n"
            f"{listing}\n"
            "题面输入只能二选一：要么 --question 传完整题面（含选项），"
            "要么 --question 只传题干、选项走 --option/--options。禁止同一组选项两边都传。"
        )
    question_lines, options_source = build_question_lines(args.question, explicit_options)
    if not question_lines:
        json_error("题目不能为空")
    validate_required_detail_fields(subject, args)
    validate_latex_wrapping(args, explicit_options)
    validate_readable_layout(subject, args)

    today_obj = parse_today(args.today)
    today = today_obj.isoformat()
    review_interval, ease_factor = compute_initial_review_schedule(args.status)
    next_review = (today_obj + timedelta(days=review_interval)).isoformat()

    try:
        chapter_resolution = resolve_wrong_card_chapter(subject, args.chapter, strict=True)
    except ValueError as exc:
        json_error(str(exc))

    relative_dir = chapter_resolution.relative_dir
    card_dir = Path(obsidian_root) / "错题本" / subject
    for segment in Path(relative_dir).parts:
        card_dir /= sanitize_path_segment(segment)
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
        "chapter_id": chapter_resolution.chapter_id,
        "chapter_path": chapter_resolution.chapter_path,
        "chapter_display": chapter_resolution.chapter_display,
        "error_tags": args.error_tag,
        "first_wrong_at": today,
        "last_review_at": today,
        "wrong_count": "1",
        "status": args.status,
        "next_review": next_review,
        "review_interval": str(review_interval),
        "ease_factor": f"{ease_factor:.2f}",
    }
    key_order = [
        "source",
        "question_id",
        "topic",
        "chapter_id",
        "chapter_path",
        "chapter_display",
        "error_tags",
        "first_wrong_at",
        "last_review_at",
        "wrong_count",
        "status",
        "next_review",
        "review_interval",
        "ease_factor",
    ]

    detail_sections = build_detail_sections(subject, args)
    body = build_card_body(
        subject=subject,
        topic=args.topic.strip(),
        source=args.source.strip(),
        question_id=args.question_id,
        question_lines=question_lines,
        detail_sections=detail_sections,
        status=args.status,
        comment=args.comment,
        today=today,
    )
    rendered_card = serialize_frontmatter(frontmatter, key_order, body)
    ensure_no_placeholder_tokens(rendered_card)
    atomic_write(output_path, rendered_card)

    print(json.dumps({
        "path": str(output_path),
        "subject": subject,
        "chapter": chapter_resolution.chapter_display or sanitize_path_segment(args.chapter),
        "chapter_id": chapter_resolution.chapter_id,
        "chapter_path": chapter_resolution.chapter_path,
        "topic": args.topic.strip(),
        "question_id": args.question_id,
        "question_line_count": len(question_lines),
        "option_count": len(explicit_options),
        "options_source": options_source,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
