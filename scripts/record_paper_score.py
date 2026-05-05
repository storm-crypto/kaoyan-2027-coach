#!/usr/bin/env python3
"""记录单张完整卷子的成绩，并同步档案摘要表。"""
import argparse
import json
from datetime import date
from typing import Dict, Optional

from archive_ops import load_archive_text, update_archive_date, upsert_subject_score_row
from env_util import atomic_write, resolve_obsidian_root
from score_record_lib import (
    SUBJECT_SCORE_FIELDS,
    build_summary_row_from_record,
    normalize_subject,
    parse_non_negative_number,
    validate_score_breakdown,
    write_score_record,
)


# 单科分数之外的失分/错题数追踪字段。score_* 字段从 SUBJECT_SCORE_FIELDS 反射,
# loss_* 字段是单独的辅助统计,不参与总分校验,因此独立列出。
LOSS_FIELDS_BY_SUBJECT: Dict[str, tuple] = {
    "数学一": ("loss_objective", "loss_big"),
    "408": (
        "loss_choice_ds",
        "loss_choice_co",
        "loss_choice_os",
        "loss_choice_cn",
        "loss_big_ds",
        "loss_big_co",
        "loss_big_os",
        "loss_big_cn",
    ),
}


def _field_to_cli(field: str) -> str:
    return "--" + field.replace("_", "-")


def _all_extra_fields() -> tuple:
    """所有 subject 用得到的字段并集,用于注册 CLI 参数。"""
    seen: list = []
    for subject_fields in SUBJECT_SCORE_FIELDS.values():
        for field in subject_fields:
            if field not in seen:
                seen.append(field)
    for subject_fields in LOSS_FIELDS_BY_SUBJECT.values():
        for field in subject_fields:
            if field not in seen:
                seen.append(field)
    return tuple(seen)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="记录单张完整卷子的成绩")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("subject", help="科目：数学一 / 408 / 英语一 / 政治")
    parser.add_argument("--paper", required=True, help="卷子名称")
    parser.add_argument("--paper-type", required=True, choices=["真题", "模拟"], help="卷型")
    parser.add_argument("--total", required=True, help="总分")
    parser.add_argument("--issues", required=True, help="本次暴露的主要问题")
    parser.add_argument("--note", default="", help="补充备注")
    parser.add_argument("--date", "--exam-date", dest="exam_date", help="考试日期 YYYY-MM-DD")

    for field in _all_extra_fields():
        parser.add_argument(_field_to_cli(field))

    return parser.parse_args()


def collect_extra_fields(subject: str, args: argparse.Namespace) -> Dict[str, Optional[float]]:
    fields: Dict[str, Optional[float]] = {}
    relevant_fields = list(SUBJECT_SCORE_FIELDS.get(subject, ())) + list(LOSS_FIELDS_BY_SUBJECT.get(subject, ()))
    for field in relevant_fields:
        cli_name = _field_to_cli(field)
        attr = field  # argparse 会把 --score-objective 转成 args.score_objective
        fields[field] = parse_non_negative_number(getattr(args, attr), cli_name.lstrip("-"))
    return fields


def main() -> None:
    args = parse_args()
    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    subject = normalize_subject(args.subject)
    exam_day = date.fromisoformat(args.exam_date).isoformat() if args.exam_date else date.today().isoformat()
    total_score = parse_non_negative_number(args.total, "total")
    assert total_score is not None

    extra_fields = collect_extra_fields(subject, args)
    validate_score_breakdown(subject, total_score, extra_fields)

    record_path = write_score_record(
        obsidian_root=obsidian_root,
        subject=subject,
        paper=args.paper,
        paper_type=args.paper_type,
        exam_day=exam_day,
        total_score=total_score,
        issues=args.issues,
        note=args.note,
        extra_fields=extra_fields,
    )

    archive_path, archive_text = load_archive_text(obsidian_root)
    updated = update_archive_date(archive_text, exam_day)
    updated = upsert_subject_score_row(
        updated,
        subject,
        build_summary_row_from_record({
            "subject": subject,
            "exam_date": exam_day,
            "paper_type": args.paper_type,
            "paper": args.paper,
            "total_score": total_score,
            "issues": args.issues,
            "note": args.note or "-",
            **extra_fields,
        }),
    )
    atomic_write(archive_path, updated)

    print(json.dumps({
        "record_path": str(record_path),
        "archive_path": str(archive_path),
        "subject": subject,
        "date": exam_day,
        "paper": args.paper,
        "paper_type": args.paper_type,
        "total_score": total_score,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
