#!/usr/bin/env python3
"""在错题本中搜索已有错题卡。

用法: python3 find_card.py [OBSIDIAN_ROOT] [科目] [关键词...]
例:   python3 find_card.py /path/to/root 数学一 二重积分 极坐标

匹配规则：
- 所有关键词必须同时出现在文件名中（AND 逻辑）
- 同时检查 frontmatter 的 topic 字段作为补充匹配

输出: JSON 对象:
  - count: 匹配数量
  - matches: 数组，每条含 path, filename, topic
  - verdict: "new"（0条匹配=新题）/ "found"（1条=旧题）/ "ambiguous"（>1条=需人工选择）
"""
import sys, json
from pathlib import Path


def parse_frontmatter_field(text, field):
    """快速提取 frontmatter 中某个字段的值。"""
    if not text.startswith("---"):
        return ""
    end = text.find("---", 3)
    if end == -1:
        return ""
    for line in text[3:end].split("\n"):
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        if key.strip() == field:
            return val.strip()
    return ""


def main():
    if len(sys.argv) < 4:
        print("用法: python3 find_card.py [OBSIDIAN_ROOT] [科目] [关键词...]", file=sys.stderr)
        sys.exit(1)

    root = Path(sys.argv[1]) / "错题本" / sys.argv[2]
    keywords = [k.lower() for k in sys.argv[3:]]

    if not root.exists():
        print(json.dumps({"count": 0, "matches": [], "verdict": "new"}, ensure_ascii=False))
        return

    matches = []
    for md_file in root.rglob("*.md"):
        name_lower = md_file.stem.lower()
        # 文件名匹配
        name_match = all(kw in name_lower for kw in keywords)

        # topic 字段补充匹配
        topic_match = False
        if not name_match:
            text = md_file.read_text(encoding="utf-8")
            topic = parse_frontmatter_field(text, "topic").lower()
            if topic and all(kw in topic for kw in keywords):
                topic_match = True

        if name_match or topic_match:
            text = md_file.read_text(encoding="utf-8") if not topic_match else text
            topic = parse_frontmatter_field(text, "topic") if name_match else topic
            matches.append({
                "path": str(md_file),
                "filename": md_file.stem,
                "topic": topic,
            })

    count = len(matches)
    if count == 0:
        verdict = "new"
    elif count == 1:
        verdict = "found"
    else:
        verdict = "ambiguous"

    print(json.dumps({
        "count": count,
        "matches": matches,
        "verdict": verdict,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
