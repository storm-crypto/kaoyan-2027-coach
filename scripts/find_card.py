#!/usr/bin/env python3
"""在错题本中搜索已有错题卡。

用法:
  python3 find_card.py [OBSIDIAN_ROOT] [科目] --question-id [QUESTION_ID] [关键词...]
  python3 find_card.py [OBSIDIAN_ROOT] [科目] [关键词...]

例:
  python3 find_card.py /path/to/root 数学一 --question-id qid-abc123def456 二重积分 极坐标
  python3 find_card.py /path/to/root 数学一 二重积分 极坐标

匹配规则：
- 优先按 frontmatter 的 question_id 精确匹配
- question_id 未命中时，再按关键词做兼容检索
- 关键词采用 AND 逻辑：文件名或 topic 字段必须同时包含全部关键词

输出: JSON 对象:
  - count: 匹配数量
  - matches: 数组，每条含 path, filename, topic, question_id, matched_by
  - verdict: "new"（0条匹配=新题）/ "found"（1条=旧题）/ "ambiguous"（>1条=需人工选择）
  - search_mode: "question_id" / "keywords" / "none"
  - needs_question_id_backfill: 是否应给旧卡回填 question_id
"""
import argparse
import json
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


def load_card_metadata(md_file):
    text = md_file.read_text(encoding="utf-8")
    return {
        "topic": parse_frontmatter_field(text, "topic"),
        "question_id": parse_frontmatter_field(text, "question_id"),
    }


def main():
    parser = argparse.ArgumentParser(description="搜索已有错题卡")
    parser.add_argument("obsidian_root", help="Obsidian 根目录")
    parser.add_argument("subject", help="科目目录名，如 数学一 / 408")
    parser.add_argument("--question-id", dest="question_id", help="优先精确匹配的 question_id")
    args, keywords = parser.parse_known_args()

    if any(keyword.startswith("-") for keyword in keywords):
        parser.error(f"无法识别的参数: {' '.join(keyword for keyword in keywords if keyword.startswith('-'))}")

    root = Path(args.obsidian_root) / "错题本" / args.subject
    keywords = [k.lower() for k in keywords]

    if not root.exists():
        print(
            json.dumps(
                {
                    "count": 0,
                    "matches": [],
                    "verdict": "new",
                    "search_mode": "none",
                    "needs_question_id_backfill": False,
                },
                ensure_ascii=False,
            )
        )
        return

    question_id_matches = []
    keyword_matches = []

    for md_file in sorted(root.rglob("*.md")):
        metadata = None

        if args.question_id:
            metadata = load_card_metadata(md_file)
            if metadata["question_id"] == args.question_id:
                question_id_matches.append(
                    {
                        "path": str(md_file),
                        "filename": md_file.stem,
                        "topic": metadata["topic"],
                        "question_id": metadata["question_id"],
                        "matched_by": "question_id",
                    }
                )
                continue

        if not keywords:
            continue

        name_lower = md_file.stem.lower()
        name_match = all(kw in name_lower for kw in keywords)

        topic_match = False
        if not name_match:
            metadata = metadata or load_card_metadata(md_file)
            topic_lower = metadata["topic"].lower()
            if topic_lower and all(kw in topic_lower for kw in keywords):
                topic_match = True

        if name_match or topic_match:
            metadata = metadata or load_card_metadata(md_file)
            keyword_matches.append(
                {
                    "path": str(md_file),
                    "filename": md_file.stem,
                    "topic": metadata["topic"],
                    "question_id": metadata["question_id"],
                    "matched_by": "filename" if name_match else "topic",
                }
            )

    if question_id_matches:
        matches = question_id_matches
        search_mode = "question_id"
    elif keyword_matches:
        matches = keyword_matches
        search_mode = "keywords"
    else:
        matches = []
        search_mode = "none"

    count = len(matches)
    if count == 0:
        verdict = "new"
    elif count == 1:
        verdict = "found"
    else:
        verdict = "ambiguous"

    print(
        json.dumps(
            {
                "count": count,
                "matches": matches,
                "verdict": verdict,
                "search_mode": search_mode,
                "needs_question_id_backfill": bool(args.question_id and search_mode == "keywords"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
