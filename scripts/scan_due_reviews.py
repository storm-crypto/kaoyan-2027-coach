#!/usr/bin/env python3
"""扫描错题本，返回今日到期的待复习错题（JSON）。
同时对超期 7 天以上的卡片自动将 review_interval 重置为 1。

用法: python3 scan_due_reviews.py [OBSIDIAN_ROOT] [--today YYYY-MM-DD]
      环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数
"""
import argparse
import json
from datetime import timedelta

from archive_ops import extract_heading_block
from frontmatter import parse_frontmatter, serialize_frontmatter
from env_util import resolve_obsidian_root, atomic_write, safe_int, is_icloud_placeholder
from study_ops import iter_review_cards, parse_today


def normalize_block(text):
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def build_question_payload(body, topic):
    question_text = normalize_block(extract_heading_block(body, "题目", level=3))
    options_text = normalize_block(extract_heading_block(body, "选项（如有）", level=3))
    preview_source = question_text or topic or "未记录题目"
    preview = "\n".join(preview_source.splitlines()[:3])
    return question_text, options_text, preview


def main():
    parser = argparse.ArgumentParser(description="扫描到期错题")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args()

    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    today = parse_today(args.today)
    threshold = today - timedelta(days=7)
    due = []
    degraded = 0
    icloud_warnings = []

    for item in iter_review_cards(obsidian_root) or []:
        if item["icloud_placeholder"]:
            icloud_warnings.append(str(item["path"]))
            continue

        fm = item["frontmatter"]
        body = item["body"]
        key_order = item["key_order"]
        next_review = item["next_review"]
        interval = item["review_interval"]
        if not fm or next_review is None:
            continue

        # 超期降级：interval 重置为 1，next_review 设为今天
        if next_review < threshold and interval > 1:
            fm["review_interval"] = "1"
            fm["next_review"] = today.isoformat()
            interval = 1
            next_review = today
            atomic_write(item["path"], serialize_frontmatter(fm, key_order, body))
            degraded += 1

        # 筛选到期且未毕业（interval < 90）
        if next_review <= today and interval < 90:
            topic = fm.get("topic", "")
            question_text, options_text, question_preview = build_question_payload(body, topic)
            due.append({
                "path": str(item["path"]),
                "subject": item["subject"],
                "topic": topic,
                "status": fm.get("status", ""),
                "review_interval": interval,
                "filename": item["path"].stem,
                "question_text": question_text,
                "options_text": options_text,
                "question_preview": question_preview,
            })

    due.sort(key=lambda x: (x["review_interval"], x["subject"]))
    result = {"due": due, "degraded": degraded}
    if icloud_warnings:
        result["icloud_placeholders"] = icloud_warnings
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
