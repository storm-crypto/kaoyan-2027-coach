#!/usr/bin/env python3
"""为已有错题卡生成红绿灯；默认只预览，--apply 落盘，仅改自动生成区块。"""
import argparse
import json

from card_progress import card_progress, upsert_card_progress
from env_util import atomic_write, resolve_obsidian_root
from frontmatter import parse_frontmatter
from study_ops import iter_review_cards


def sync_progress(root, apply=False):
    result = {"dry_run": not apply, "cards": 0, "updated_cards": 0,
              "without_history": 0, "written": 0, "skipped_placeholders": 0}
    for card in iter_review_cards(root):
        if card["icloud_placeholder"]:
            result["skipped_placeholders"] += 1
            continue
        fm = card["frontmatter"]
        if not fm.get("question_id") and not fm.get("first_wrong_at"):
            continue
        result["cards"] += 1
        path = card["path"]
        text = path.read_text(encoding="utf-8")
        _, body, _ = parse_frontmatter(text)
        if not card_progress(body)["attempts"]:
            result["without_history"] += 1
        updated = upsert_card_progress(body)
        if updated == body:
            continue
        result["updated_cards"] += 1
        if apply:
            # 保留原 YAML 字节布局，绝不重序列化或回写学习状态。
            atomic_write(path, text[:len(text) - len(body)] + updated)
            result["written"] += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("obsidian_root", nargs="?")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(sync_progress(resolve_obsidian_root(args.obsidian_root), args.apply),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
