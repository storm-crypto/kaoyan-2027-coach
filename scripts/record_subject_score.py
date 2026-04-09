#!/usr/bin/env python3
"""记录数学一/408 单科模拟成绩到学习者档案。"""
import argparse
import json
from datetime import date

from archive_ops import (
    format_number,
    load_archive_text,
    update_archive_date,
    upsert_subject_score_row,
)
from env_util import atomic_write, json_error, resolve_obsidian_root


ALIASES = {"数学": "数学一"}


def parse_number(value: str, label: str) -> float:
    try:
        number = float(value)
    except ValueError:
        json_error(f"{label} 必须是数字")
    if number < 0:
        json_error(f"{label} 不能小于 0")
    return number


def parse_args():
    parser = argparse.ArgumentParser(description="记录数学一/408 单科模拟成绩")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("subject", help="科目：数学一/数学/408")
    parser.add_argument("--date", dest="score_date", help="记录日期 YYYY-MM-DD")
    parser.add_argument("--paper", required=True, help="卷子名称")
    parser.add_argument("--score", help="数学一成绩")
    parser.add_argument("--ds", help="408 数据结构错题数/失分题数")
    parser.add_argument("--co", help="408 组成原理错题数/失分题数")
    parser.add_argument("--os", help="408 操作系统错题数/失分题数")
    parser.add_argument("--cn", help="408 计算机网络错题数/失分题数")
    parser.add_argument("--total", help="408 总分")
    parser.add_argument("--issues", required=True, help="本次暴露的主要问题")
    parser.add_argument("--note", default="", help="补充备注")
    return parser.parse_args()


def build_row(args, record_day: str):
    subject = ALIASES.get(args.subject, args.subject)
    note = args.note or "-"
    if subject == "数学一":
        if not args.score:
            json_error("数学一 需要传 --score")
        return subject, {
            "date": record_day,
            "paper": args.paper,
            "score": format_number(parse_number(args.score, "score")),
            "issues": args.issues,
            "note": note,
        }

    if subject == "408":
        required = {
            "ds": args.ds,
            "co": args.co,
            "os": args.os,
            "cn": args.cn,
            "total": args.total,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            json_error(f"408 缺少参数: {', '.join(missing)}")
        return subject, {
            "date": record_day,
            "paper": args.paper,
            "ds": format_number(parse_number(args.ds, "ds")),
            "co": format_number(parse_number(args.co, "co")),
            "os": format_number(parse_number(args.os, "os")),
            "cn": format_number(parse_number(args.cn, "cn")),
            "total": format_number(parse_number(args.total, "total")),
            "issues": args.issues,
            "note": note,
        }

    json_error(f"不支持的科目: {args.subject}")


def main():
    args = parse_args()
    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    record_day = date.fromisoformat(args.score_date).isoformat() if args.score_date else date.today().isoformat()
    subject, row = build_row(args, record_day)

    archive_path, archive_text = load_archive_text(obsidian_root)
    updated = update_archive_date(archive_text, record_day)
    updated = upsert_subject_score_row(updated, subject, row)
    atomic_write(archive_path, updated)

    print(json.dumps({
        "archive": str(archive_path),
        "subject": subject,
        "date": record_day,
        "paper": args.paper,
        "section": f"{subject}模拟成绩追踪",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
