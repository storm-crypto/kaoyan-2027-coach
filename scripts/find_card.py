#!/usr/bin/env python3
"""在错题本中搜索已有错题卡。

用法:
  python3 find_card.py [OBSIDIAN_ROOT] [科目] --question-id [QUESTION_ID] [关键词...]
  python3 find_card.py [科目] --question-id [QUESTION_ID] [关键词...]
  环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数

匹配规则：
- 优先按 frontmatter 的 question_id 精确匹配；该匹配会跨科扫描整个错题本
- 默认情况下，question_id 未命中时不会自动降级为关键词命中，避免误把新题合并到旧卡
- 仅在显式传入 --legacy-fallback 时，question_id 未命中后才按当前科目下的关键词做兼容检索
- 关键词采用 AND 逻辑：文件名或 topic 字段必须同时包含全部关键词

输出: JSON 对象:
  - count, matches, verdict ("new"/"found"/"ambiguous"), search_mode, needs_question_id_backfill
  - keyword_candidates: 仅在 qid 未命中且存在候选旧卡时返回，供人工确认
"""
import argparse
import json
from pathlib import Path

from frontmatter import parse_frontmatter_field
from env_util import resolve_obsidian_root, is_icloud_placeholder


def load_card_metadata(md_file):
    text = md_file.read_text(encoding="utf-8")
    return {
        "topic": parse_frontmatter_field(text, "topic"),
        "question_id": parse_frontmatter_field(text, "question_id"),
    }


def main():
    parser = argparse.ArgumentParser(description="搜索已有错题卡")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian 根目录（可由环境变量替代）")
    parser.add_argument("subject", help="科目目录名，如 数学一 / 408")
    parser.add_argument("--question-id", dest="question_id", help="优先精确匹配的 question_id")
    parser.add_argument(
        "--legacy-fallback",
        action="store_true",
        help="question_id 未命中时允许按关键词兼容命中旧卡（仅用于迁移旧库）",
    )
    args, keywords = parser.parse_known_args()

    if any(keyword.startswith("-") for keyword in keywords):
        parser.error(f"无法识别的参数: {' '.join(keyword for keyword in keywords if keyword.startswith('-'))}")

    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    root = obsidian_root / "错题本"
    subject_root = root / args.subject
    keywords = [k.lower() for k in keywords]
    icloud_warnings = []

    if not root.exists():
        print(json.dumps({
            "count": 0, "matches": [], "verdict": "new",
            "search_mode": "none", "needs_question_id_backfill": False,
        }, ensure_ascii=False))
        return

    question_id_matches = []
    keyword_matches = []

    for md_file in sorted(root.rglob("*.md")):
        if is_icloud_placeholder(md_file):
            icloud_warnings.append(str(md_file))
            continue

        try:
            try:
                md_file.relative_to(subject_root)
                in_subject_scope = True
            except ValueError:
                in_subject_scope = False

            metadata = None
            if args.question_id:
                metadata = load_card_metadata(md_file)
                if metadata["question_id"] == args.question_id:
                    question_id_matches.append({
                        "path": str(md_file), "filename": md_file.stem,
                        "topic": metadata["topic"], "question_id": metadata["question_id"],
                        "matched_by": "question_id",
                    })
                    continue

            if not keywords or not in_subject_scope:
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
                keyword_matches.append({
                    "path": str(md_file), "filename": md_file.stem,
                    "topic": metadata["topic"], "question_id": metadata["question_id"],
                    "matched_by": "filename" if name_match else "topic",
                })
        except (OSError, UnicodeDecodeError):
            continue

    keyword_candidates = []
    if question_id_matches:
        matches, search_mode = question_id_matches, "question_id"
    elif args.question_id and keyword_matches and not args.legacy_fallback:
        matches, search_mode = [], "question_id_miss"
        keyword_candidates = keyword_matches
    elif keyword_matches:
        matches, search_mode = keyword_matches, "keywords"
    else:
        matches, search_mode = [], ("question_id_miss" if args.question_id else "none")

    count = len(matches)
    verdict = "new" if count == 0 else ("found" if count == 1 else "ambiguous")

    result = {
        "count": count, "matches": matches, "verdict": verdict,
        "search_mode": search_mode,
        "needs_question_id_backfill": bool(args.question_id and search_mode == "keywords"),
    }
    if keyword_candidates:
        result["keyword_candidates"] = keyword_candidates
    if icloud_warnings:
        result["icloud_placeholders"] = icloud_warnings
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
