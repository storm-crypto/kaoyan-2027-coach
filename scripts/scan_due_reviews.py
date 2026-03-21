#!/usr/bin/env python3
"""扫描错题本，返回今日到期的待复习错题（JSON）。
同时对超期 7 天以上的卡片自动将 review_interval 重置为 1。

用法: python3 scan_due_reviews.py [OBSIDIAN_ROOT]
      环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数
"""
import sys
import json
from datetime import date, timedelta
from pathlib import Path

from frontmatter import parse_frontmatter, serialize_frontmatter
from env_util import resolve_obsidian_root, atomic_write, safe_int, is_icloud_placeholder


def main():
    cli_arg = sys.argv[1] if len(sys.argv) > 1 else None
    root = resolve_obsidian_root(cli_arg) / "错题本"

    if not root.exists():
        print(json.dumps({"due": [], "degraded": 0, "icloud_placeholders": []}))
        return

    today = date.today()
    threshold = today - timedelta(days=7)
    due = []
    degraded = 0
    icloud_warnings = []

    for md_file in root.rglob("*.md"):
        if is_icloud_placeholder(md_file):
            icloud_warnings.append(str(md_file))
            continue

        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        fm, body, key_order = parse_frontmatter(text)
        if not fm or "next_review" not in fm:
            continue

        try:
            next_review = date.fromisoformat(fm["next_review"])
        except (ValueError, TypeError):
            continue

        interval = safe_int(fm.get("review_interval", 1))

        # 超期降级：interval 重置为 1，next_review 设为今天
        if next_review < threshold and interval > 1:
            fm["review_interval"] = "1"
            fm["next_review"] = today.isoformat()
            interval = 1
            next_review = today
            atomic_write(md_file, serialize_frontmatter(fm, key_order, body))
            degraded += 1

        # 筛选到期且未毕业（interval < 90）
        if next_review <= today and interval < 90:
            rel = md_file.relative_to(root)
            subject = rel.parts[0] if rel.parts else "未知"
            due.append({
                "path": str(md_file),
                "subject": subject,
                "topic": fm.get("topic", ""),
                "status": fm.get("status", ""),
                "review_interval": interval,
                "filename": md_file.stem,
            })

    due.sort(key=lambda x: (x["review_interval"], x["subject"]))
    result = {"due": due, "degraded": degraded}
    if icloud_warnings:
        result["icloud_placeholders"] = icloud_warnings
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
