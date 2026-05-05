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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="记录单张完整卷子的成绩")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("subject", help="科目：数学一 / 408 / 英语一")
    parser.add_argument("--paper", required=True, help="卷子名称")
    parser.add_argument("--paper-type", required=True, choices=["真题", "模拟"], help="卷型")
    parser.add_argument("--total", required=True, help="总分")
    parser.add_argument("--issues", required=True, help="本次暴露的主要问题")
    parser.add_argument("--note", default="", help="补充备注")
    parser.add_argument("--date", "--exam-date", dest="exam_date", help="考试日期 YYYY-MM-DD")

    parser.add_argument("--score-objective", help="数学一：选填得分")
    parser.add_argument("--score-big", help="数学一：大题得分")
    parser.add_argument("--loss-objective", help="数学一：选填失分/错题数")
    parser.add_argument("--loss-big", help="数学一：大题失分/错题数")

    for prefix in ("score-choice", "score-big", "loss-choice", "loss-big"):
        parser.add_argument(f"--{prefix}-ds")
        parser.add_argument(f"--{prefix}-co")
        parser.add_argument(f"--{prefix}-os")
        parser.add_argument(f"--{prefix}-cn")

    parser.add_argument("--score-cloze", help="英语一：完形得分")
    parser.add_argument("--score-reading", help="英语一：阅读得分")
    parser.add_argument("--score-new-type", help="英语一：新题型得分")
    parser.add_argument("--score-translation", help="英语一：翻译得分")
    parser.add_argument("--score-short-essay", help="英语一：小作文得分")
    parser.add_argument("--score-long-essay", help="英语一：大作文得分")
    return parser.parse_args()


def collect_extra_fields(subject: str, args: argparse.Namespace) -> Dict[str, Optional[float]]:
    fields: Dict[str, Optional[float]] = {}
    if subject == "数学一":
        fields["score_objective"] = parse_non_negative_number(args.score_objective, "score-objective")
        fields["score_big"] = parse_non_negative_number(args.score_big, "score-big")
        fields["loss_objective"] = parse_non_negative_number(args.loss_objective, "loss-objective")
        fields["loss_big"] = parse_non_negative_number(args.loss_big, "loss-big")
        return fields

    if subject == "408":
        for field in (
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
        ):
            cli_name = field.replace("_", "-")
            fields[field] = parse_non_negative_number(getattr(args, cli_name.replace("-", "_")), cli_name)
        return fields

    if subject == "英语一":
        for field in SUBJECT_SCORE_FIELDS["英语一"]:
            cli_name = field.replace("_", "-")
            fields[field] = parse_non_negative_number(getattr(args, cli_name.replace("-", "_")), cli_name)
        return fields

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
            "exam_date": exam_day,
            "paper_type": args.paper_type,
            "paper": args.paper,
            "total_score": total_score,
            "issues": args.issues,
            "note": args.note or "-",
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
