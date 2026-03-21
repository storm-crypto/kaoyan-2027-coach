#!/usr/bin/env python3
"""更新知识地图中指定考点的掌握度和备注。

用法: python3 update_knowledge_map.py [OBSIDIAN_ROOT] [科目] [考点关键词] [掌握度] [备注]
例:   python3 update_knowledge_map.py /path/to/root 数学一 二重积分 半会 "极坐标变换不熟"

科目映射: 数学一→数学一.md, 408→408.md, 政治→政治.md, 英语一→英语一.md
"""
import sys, re
from pathlib import Path

SUBJECT_MAP = {
    "数学一": "数学一.md", "数学": "数学一.md",
    "408": "408.md",
    "政治": "政治.md",
    "英语一": "英语一.md", "英语": "英语一.md",
}


def main():
    if len(sys.argv) < 5:
        print("用法: python3 update_knowledge_map.py [OBSIDIAN_ROOT] [科目] [考点关键词] [掌握度] [备注(可选)]", file=sys.stderr)
        sys.exit(1)

    root = Path(sys.argv[1]) / "知识地图"
    subject = sys.argv[2]
    keyword = sys.argv[3]
    mastery = sys.argv[4]
    note = sys.argv[5] if len(sys.argv) > 5 else ""

    filename = SUBJECT_MAP.get(subject)
    if not filename:
        print(f"错误: 未知科目 '{subject}'，支持: {', '.join(SUBJECT_MAP.keys())}", file=sys.stderr)
        sys.exit(1)

    filepath = root / filename
    if not filepath.exists():
        print(f"错误: 文件不存在 {filepath}", file=sys.stderr)
        sys.exit(1)

    lines = filepath.read_text(encoding="utf-8").split("\n")
    updated = False

    for i, line in enumerate(lines):
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        # 表格行格式: | 考点 | 掌握度 | 信心 | 备注 |
        # cells[0] 和 cells[-1] 是空字符串（|分隔产生的）
        if len(cells) < 5:
            continue
        topic_cell = cells[1]
        if keyword.lower() in topic_cell.lower():
            # 更新掌握度（第3列）和备注（第5列）
            cells[2] = f" {mastery} "
            if note:
                cells[4] = f" {note} "
            lines[i] = "|".join(cells)
            updated = True
            print(f"已更新: {topic_cell.strip()} → 掌握度={mastery}" + (f", 备注={note}" if note else ""))
            break

    if not updated:
        print(f"警告: 未找到包含 '{keyword}' 的考点行", file=sys.stderr)
        sys.exit(1)

    filepath.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
