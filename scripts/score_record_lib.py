"""成绩记录共享工具：卷子级成绩记录的落盘、读取和字段校验。"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from archive_ops import format_number
from env_util import atomic_write, json_error
from frontmatter import Frontmatter, parse_frontmatter, serialize_frontmatter

SUBJECT_ALIASES = {
    "数学": "数学一",
    "数学一": "数学一",
    "408": "408",
    "英语": "英语一",
    "英语一": "英语一",
    "政治": "政治",
}

SUBJECT_TOTALS = {
    "数学一": 150.0,
    "408": 150.0,
    "英语一": 100.0,
    "政治": 100.0,
}

SUBJECT_SCORE_FIELDS = {
    "数学一": ("score_objective", "score_big"),
    "408": (
        "score_choice_ds",
        "score_choice_co",
        "score_choice_os",
        "score_choice_cn",
        "score_big_ds",
        "score_big_co",
        "score_big_os",
        "score_big_cn",
    ),
    "英语一": (
        "score_cloze",
        "score_reading",
        "score_new_type",
        "score_translation",
        "score_short_essay",
        "score_long_essay",
    ),
    # 政治单卷只记录总分 + 主要问题 + 备注,不做 breakdown。
    "政治": (),
}

RECORD_KEY_ORDER = [
    "subject",
    "paper",
    "paper_type",
    "exam_date",
    "total_score",
    "issues",
    "note",
    "score_objective",
    "score_big",
    "loss_objective",
    "loss_big",
    "score_choice_ds",
    "score_choice_co",
    "score_choice_os",
    "score_choice_cn",
    "score_big_ds",
    "score_big_co",
    "score_big_os",
    "score_big_cn",
    "loss_choice_ds",
    "loss_choice_co",
    "loss_choice_os",
    "loss_choice_cn",
    "loss_big_ds",
    "loss_big_co",
    "loss_big_os",
    "loss_big_cn",
    "score_cloze",
    "score_reading",
    "score_new_type",
    "score_translation",
    "score_short_essay",
    "score_long_essay",
]

INVALID_PATH_CHARS_RE = re.compile(r'[\\/:*?"<>|]+')
WHITESPACE_RE = re.compile(r"\s+")

# 总分与细分之和允许的最大偏差。英语一阅读 2 分一题但部分模拟卷会出现
# 0.5 粒度的部分给分,且浮点累加也会有微误差,所以容忍到 0.6 分。
SCORE_TOTAL_TOLERANCE = 0.6


def normalize_subject(subject: str) -> str:
    normalized = SUBJECT_ALIASES.get(subject)
    if not normalized:
        legal = sorted(set(SUBJECT_ALIASES))
        json_error(f"不支持的科目: {subject},合法值: {legal}")
    return normalized


def parse_non_negative_number(value: Optional[str], label: str) -> Optional[float]:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except ValueError:
        json_error(f"{label} 必须是数字")
    if number < 0:
        json_error(f"{label} 不能小于 0")
    return number


def infer_paper_type(paper: str) -> str:
    if "真题" in paper:
        return "真题"
    return "模拟"


def sanitize_filename_segment(text: str) -> str:
    value = INVALID_PATH_CHARS_RE.sub("-", text.strip())
    value = WHITESPACE_RE.sub("-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-.")
    return value or "未命名"


def format_optional_number(value: Optional[float]) -> str:
    if value is None:
        return ""
    return format_number(value)


def build_record_path(obsidian_root: Path, subject: str, exam_day: str, paper_type: str, paper: str) -> Path:
    filename = f"{exam_day}-{sanitize_filename_segment(paper_type)}-{sanitize_filename_segment(paper)}.md"
    return Path(obsidian_root) / "成绩记录" / subject / filename


def validate_score_breakdown(subject: str, total_score: float, fields: Mapping[str, Optional[float]]) -> None:
    score_fields = SUBJECT_SCORE_FIELDS.get(subject, ())
    provided = [fields.get(field) for field in score_fields]
    if not provided or any(value is None for value in provided):
        return

    breakdown_total = sum(value for value in provided if value is not None)
    if abs(breakdown_total - total_score) > SCORE_TOTAL_TOLERANCE:
        json_error(f"{subject} 细分得分之和 {format_number(breakdown_total)} 与总分 {format_number(total_score)} 不一致")


def build_record_body(subject: str, data: Mapping[str, str]) -> str:
    lines = [
        f"# 成绩记录：{subject} / {data['paper']}",
        "",
        "## 摘要",
        f"- **卷型**：{data['paper_type']}",
        f"- **日期**：{data['exam_date']}",
        f"- **总分**：{data['total_score']}",
        f"- **主要问题**：{data['issues']}",
        f"- **备注**：{data['note'] or '-'}",
    ]

    detail_lines: List[str] = []
    if subject == "数学一":
        if data.get("score_objective") or data.get("score_big"):
            detail_lines.extend([
                "",
                "## 细分得分",
                f"- 选填：{data.get('score_objective') or '-'}",
                f"- 大题：{data.get('score_big') or '-'}",
            ])
        if data.get("loss_objective") or data.get("loss_big"):
            detail_lines.extend([
                "",
                "## 失分记录",
                f"- 选填失分：{data.get('loss_objective') or '-'}",
                f"- 大题失分：{data.get('loss_big') or '-'}",
            ])
    elif subject == "408":
        if any(data.get(field) for field in SUBJECT_SCORE_FIELDS["408"]):
            detail_lines.extend([
                "",
                "## 实际得分",
                f"- 选择题：DS {data.get('score_choice_ds') or '-'} / CO {data.get('score_choice_co') or '-'} / OS {data.get('score_choice_os') or '-'} / CN {data.get('score_choice_cn') or '-'}",
                f"- 大题：DS {data.get('score_big_ds') or '-'} / CO {data.get('score_big_co') or '-'} / OS {data.get('score_big_os') or '-'} / CN {data.get('score_big_cn') or '-'}",
            ])
        if any(data.get(field) for field in ("loss_choice_ds", "loss_choice_co", "loss_choice_os", "loss_choice_cn", "loss_big_ds", "loss_big_co", "loss_big_os", "loss_big_cn")):
            detail_lines.extend([
                "",
                "## 失分/错题数",
                f"- 选择题：DS {data.get('loss_choice_ds') or '-'} / CO {data.get('loss_choice_co') or '-'} / OS {data.get('loss_choice_os') or '-'} / CN {data.get('loss_choice_cn') or '-'}",
                f"- 大题：DS {data.get('loss_big_ds') or '-'} / CO {data.get('loss_big_co') or '-'} / OS {data.get('loss_big_os') or '-'} / CN {data.get('loss_big_cn') or '-'}",
            ])
    elif subject == "英语一":
        if any(data.get(field) for field in SUBJECT_SCORE_FIELDS["英语一"]):
            detail_lines.extend([
                "",
                "## 细分得分",
                f"- 完形：{data.get('score_cloze') or '-'}",
                f"- 阅读：{data.get('score_reading') or '-'}",
                f"- 新题型：{data.get('score_new_type') or '-'}",
                f"- 翻译：{data.get('score_translation') or '-'}",
                f"- 小作文：{data.get('score_short_essay') or '-'}",
                f"- 大作文：{data.get('score_long_essay') or '-'}",
            ])
    lines.extend(detail_lines)
    lines.append("")
    return "\n".join(lines)


def write_score_record(
    obsidian_root: Path,
    subject: str,
    paper: str,
    paper_type: str,
    exam_day: str,
    total_score: float,
    issues: str,
    note: str,
    extra_fields: Mapping[str, Optional[float]],
) -> Path:
    record_path = build_record_path(obsidian_root, subject, exam_day, paper_type, paper)
    record_path.parent.mkdir(parents=True, exist_ok=True)

    fm: Frontmatter = {
        "subject": subject,
        "paper": paper,
        "paper_type": paper_type,
        "exam_date": exam_day,
        "total_score": format_number(total_score),
        "issues": issues,
        "note": note or "",
    }
    for field, value in extra_fields.items():
        if value is None:
            continue
        fm[field] = format_number(value)

    body = "\n" + build_record_body(subject, {key: str(value) for key, value in fm.items()}) + "\n"
    atomic_write(record_path, serialize_frontmatter(fm, RECORD_KEY_ORDER, body))
    return record_path


def parse_record_numeric(value: object) -> Optional[float]:
    if value in {None, ""}:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def parse_score_record(path: Path) -> Optional[Dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    fm, body, key_order = parse_frontmatter(text)
    raw_subject = str(fm.get("subject", "")).strip()
    subject = SUBJECT_ALIASES.get(raw_subject, "")
    if not subject:
        return None
    record = {
        "path": str(path),
        "subject": subject,
        "paper": str(fm.get("paper", "")).strip(),
        "paper_type": str(fm.get("paper_type", "")).strip() or infer_paper_type(str(fm.get("paper", ""))),
        "exam_date": str(fm.get("exam_date", "")).strip(),
        "total_score": parse_record_numeric(fm.get("total_score")),
        "issues": str(fm.get("issues", "")).strip(),
        "note": str(fm.get("note", "")).strip(),
        "frontmatter": fm,
        "body": body,
        "key_order": key_order,
    }
    for field in RECORD_KEY_ORDER:
        if field.startswith("score_") or field.startswith("loss_"):
            record[field] = parse_record_numeric(fm.get(field))
    return record


def collect_score_records(obsidian_root: Path, subjects: Optional[Sequence[str]] = None) -> List[Dict[str, object]]:
    root = Path(obsidian_root) / "成绩记录"
    if not root.exists():
        return []

    subject_set = set(subjects) if subjects else None
    records: List[Dict[str, object]] = []
    for record_path in sorted(root.rglob("*.md")):
        try:
            record = parse_score_record(record_path)
        except (OSError, UnicodeDecodeError):
            continue
        if not record:
            continue
        if subject_set and record["subject"] not in subject_set:
            continue
        records.append(record)

    records.sort(key=lambda item: (item.get("exam_date", ""), item.get("paper_type", ""), item.get("paper", "")))
    return records


def build_summary_row_from_record(record: Mapping[str, object]) -> Dict[str, str]:
    subject = str(record.get("subject", "")).strip()
    base = {
        "date": str(record["exam_date"]),
        "paper_type": str(record["paper_type"]),
        "paper": str(record["paper"]),
        "total": format_number(float(record["total_score"])),
        "issues": str(record["issues"]),
        "note": str(record["note"] or "-"),
    }
    if subject != "408":
        return base

    module_totals = {}
    for label, choice_field, big_field in (
        ("ds", "score_choice_ds", "score_big_ds"),
        ("co", "score_choice_co", "score_big_co"),
        ("os", "score_choice_os", "score_big_os"),
        ("cn", "score_choice_cn", "score_big_cn"),
    ):
        choice = record.get(choice_field)
        big = record.get(big_field)
        total = 0.0
        has_value = False
        if isinstance(choice, (int, float)):
            total += float(choice)
            has_value = True
        if isinstance(big, (int, float)):
            total += float(big)
            has_value = True
        module_totals[label] = format_number(total) if has_value else ""
    return {
        **base,
        "ds": module_totals["ds"],
        "co": module_totals["co"],
        "os": module_totals["os"],
        "cn": module_totals["cn"],
    }


def top_weakness_from_408_record(record: Mapping[str, object]) -> str:
    score_pairs = {
        "DS": sum(value for value in (record.get("score_choice_ds"), record.get("score_big_ds")) if isinstance(value, float)),
        "CO": sum(value for value in (record.get("score_choice_co"), record.get("score_big_co")) if isinstance(value, float)),
        "OS": sum(value for value in (record.get("score_choice_os"), record.get("score_big_os")) if isinstance(value, float)),
        "CN": sum(value for value in (record.get("score_choice_cn"), record.get("score_big_cn")) if isinstance(value, float)),
    }
    available_scores = {key: value for key, value in score_pairs.items() if value > 0}
    if available_scores:
        weakest = min(available_scores.items(), key=lambda item: item[1])[0]
        return weakest

    loss_pairs = {
        "DS": sum(value for value in (record.get("loss_choice_ds"), record.get("loss_big_ds")) if isinstance(value, float)),
        "CO": sum(value for value in (record.get("loss_choice_co"), record.get("loss_big_co")) if isinstance(value, float)),
        "OS": sum(value for value in (record.get("loss_choice_os"), record.get("loss_big_os")) if isinstance(value, float)),
        "CN": sum(value for value in (record.get("loss_choice_cn"), record.get("loss_big_cn")) if isinstance(value, float)),
    }
    available_losses = {key: value for key, value in loss_pairs.items() if value > 0}
    if available_losses:
        weakest = max(available_losses.items(), key=lambda item: item[1])[0]
        return weakest

    return ""
