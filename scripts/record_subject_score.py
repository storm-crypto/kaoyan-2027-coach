#!/usr/bin/env python3
"""旧版数学一/408 单科成绩入口；内部转调新的卷子级成绩记录逻辑。"""
import argparse
import json
from datetime import date
from typing import Dict, Optional

from env_util import resolve_obsidian_root
from score_record_lib import infer_paper_type, normalize_subject
from score_record_lib import parse_non_negative_number, validate_score_breakdown, write_score_record, build_summary_row_from_record
from archive_ops import load_archive_text, update_archive_date, upsert_subject_score_row
from env_util import atomic_write, json_error


def parse_args():
    parser = argparse.ArgumentParser(description="记录数学一/408 单科模拟成绩")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("subject", help="科目：数学一/数学/408")
    parser.add_argument("--date", dest="score_date", help="记录日期 YYYY-MM-DD")
    parser.add_argument("--paper", required=True, help="卷子名称")
    parser.add_argument("--score", help="数学一成绩")
    parser.add_argument("--ds", help="408 数据结构得分/失分题数")
    parser.add_argument("--co", help="408 组成原理得分/失分题数")
    parser.add_argument("--os", help="408 操作系统得分/失分题数")
    parser.add_argument("--cn", help="408 计算机网络得分/失分题数")
    parser.add_argument("--total", help="408 总分")
    parser.add_argument("--issues", required=True, help="本次暴露的主要问题")
    parser.add_argument("--note", default="", help="补充备注")
    return parser.parse_args()


def build_extra_fields(subject: str, args: argparse.Namespace) -> Dict[str, Optional[float]]:
    if subject == "数学一":
        score = parse_non_negative_number(args.score, "score")
        if score is None:
            json_error("数学一 需要传 --score")
        return {"score_objective": None, "score_big": None}

    if subject == "408":
        required = {"ds": args.ds, "co": args.co, "os": args.os, "cn": args.cn, "total": args.total}
        missing = [name for name, value in required.items() if value is None]
        if missing:
            json_error(f"408 缺少参数: {', '.join(missing)}")
        return {
            "score_choice_ds": parse_non_negative_number(args.ds, "ds"),
            "score_choice_co": parse_non_negative_number(args.co, "co"),
            "score_choice_os": parse_non_negative_number(args.os, "os"),
            "score_choice_cn": parse_non_negative_number(args.cn, "cn"),
            "score_big_ds": None,
            "score_big_co": None,
            "score_big_os": None,
            "score_big_cn": None,
        }

    return {}


def main():
    args = parse_args()
    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    subject = normalize_subject(args.subject)
    record_day = date.fromisoformat(args.score_date).isoformat() if args.score_date else date.today().isoformat()
    paper_type = infer_paper_type(args.paper)

    if subject == "数学一":
        total_score = parse_non_negative_number(args.score, "score")
        assert total_score is not None
    elif subject == "408":
        total_score = parse_non_negative_number(args.total, "total")
        assert total_score is not None
    else:
        json_error(f"record_subject_score.py 不支持的科目: {subject}")

    extra_fields = build_extra_fields(subject, args)
    validate_score_breakdown(subject, total_score, extra_fields)
    record_path = write_score_record(
        obsidian_root=obsidian_root,
        subject=subject,
        paper=args.paper,
        paper_type=paper_type,
        exam_day=record_day,
        total_score=total_score,
        issues=args.issues,
        note=args.note,
        extra_fields=extra_fields,
    )

    archive_path, archive_text = load_archive_text(obsidian_root)
    updated = update_archive_date(archive_text, record_day)
    updated = upsert_subject_score_row(
        updated,
        subject,
        build_summary_row_from_record({
            "exam_date": record_day,
            "paper_type": paper_type,
            "paper": args.paper,
            "total_score": total_score,
            "issues": args.issues,
            "note": args.note or "-",
        }),
    )
    atomic_write(archive_path, updated)

    print(json.dumps({
        "archive": str(archive_path),
        "record_path": str(record_path),
        "subject": subject,
        "date": record_day,
        "paper": args.paper,
        "paper_type": paper_type,
        "section": f"{subject}模拟成绩追踪",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
