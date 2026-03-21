#!/usr/bin/env python3
"""在错题本中按关键词搜索已有错题卡。

用法: python3 find_card.py [OBSIDIAN_ROOT] [科目] [关键词...]
例:   python3 find_card.py /path/to/root 数学一 二重积分 极坐标

输出: JSON 数组，每条含 path 和 filename。空数组表示新题。
"""
import sys, json
from pathlib import Path


def main():
    if len(sys.argv) < 4:
        print("用法: python3 find_card.py [OBSIDIAN_ROOT] [科目] [关键词...]", file=sys.stderr)
        sys.exit(1)

    root = Path(sys.argv[1]) / "错题本" / sys.argv[2]
    keywords = [k.lower() for k in sys.argv[3:]]

    if not root.exists():
        print(json.dumps([]))
        return

    matches = []
    for md_file in root.rglob("*.md"):
        name_lower = md_file.stem.lower()
        if all(kw in name_lower for kw in keywords):
            matches.append({
                "path": str(md_file),
                "filename": md_file.stem,
            })

    print(json.dumps(matches, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
