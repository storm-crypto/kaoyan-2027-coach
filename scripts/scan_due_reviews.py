#!/usr/bin/env python3
"""扫描错题本，返回今日到期的待复习错题（JSON）。
同时对超期 7 天以上的卡片自动将 review_interval 重置为 1。

用法: python3 scan_due_reviews.py [OBSIDIAN_ROOT]
"""
import sys, os, json, re
from datetime import date, timedelta
from pathlib import Path


def parse_frontmatter(text):
    """解析 --- 包裹的 YAML frontmatter，返回 dict 和 frontmatter 结束位置。"""
    if not text.startswith("---"):
        return {}, 0
    end = text.find("---", 3)
    if end == -1:
        return {}, 0
    fm_text = text[3:end].strip()
    fm = {}
    for line in fm_text.split("\n"):
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            items = val[1:-1]
            fm[key] = [x.strip() for x in items.split(",") if x.strip()] if items else []
        else:
            fm[key] = val
    return fm, end + 3


def write_frontmatter(fm, body):
    """将 dict 序列化为 YAML frontmatter + body。"""
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(v)}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + body


def main():
    if len(sys.argv) < 2:
        print("用法: python3 scan_due_reviews.py [OBSIDIAN_ROOT]", file=sys.stderr)
        sys.exit(1)

    root = Path(sys.argv[1]) / "错题本"
    if not root.exists():
        print(json.dumps({"due": [], "degraded": 0}))
        return

    today = date.today()
    threshold = today - timedelta(days=7)
    due = []
    degraded = 0

    for md_file in root.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        fm, fm_end = parse_frontmatter(text)
        if not fm or "next_review" not in fm:
            continue

        try:
            next_review = date.fromisoformat(fm["next_review"])
        except (ValueError, TypeError):
            continue

        interval = int(fm.get("review_interval", 1))

        # 超期降级
        if next_review < threshold and interval > 1:
            fm["review_interval"] = "1"
            interval = 1
            body = text[fm_end:]
            md_file.write_text(write_frontmatter(fm, body), encoding="utf-8")
            degraded += 1

        # 筛选到期且未毕业
        if next_review <= today and interval < 30:
            # 从路径提取科目
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

    # 按 review_interval 升序（最差的排前面），再按科目分组
    due.sort(key=lambda x: (x["review_interval"], x["subject"]))
    print(json.dumps({"due": due, "degraded": degraded}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
