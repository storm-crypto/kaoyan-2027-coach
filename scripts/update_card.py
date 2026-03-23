#!/usr/bin/env python3
"""更新错题卡的 YAML frontmatter 并追加历史记录。

用法: python3 update_card.py [卡片路径] --status [不会/半会/会] [--comment 简评] [--question-id QUESTION_ID] [--today YYYY-MM-DD]

自动处理:
- 更新 status, last_review_at, wrong_count, next_review, review_interval, ease_factor
- 根据 status 调整 review_interval 和 ease_factor（改进版 SRS）
- 回填 question_id 时，将旧卡重命名为规范文件名
- 在"### 历史记录"下追加一行
"""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import re

from frontmatter import parse_frontmatter, serialize_frontmatter
from env_util import atomic_write, json_error, safe_int, safe_float


QID_SUFFIX_RE = re.compile(r"-qid-[0-9a-f]{12}$")
QUESTION_ID_RE = re.compile(r"^qid-[0-9a-f]{12}$")


def canonicalize_card_path(card, question_id):
    """将卡片文件名规范化为追加 question_id 的形式。"""
    stem = card.stem
    desired_suffix = f"-{question_id}"
    if stem.endswith(desired_suffix):
        return card
    if QID_SUFFIX_RE.search(stem):
        new_stem = QID_SUFFIX_RE.sub(desired_suffix, stem)
    else:
        new_stem = f"{stem}{desired_suffix}"
    return card.with_name(new_stem + card.suffix)


def parse_today(value):
    return date.fromisoformat(value) if value else date.today()


def is_within_root(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_card_path(raw_path):
    card = Path(raw_path).resolve(strict=True)
    if card.suffix.lower() != ".md":
        json_error(f"只允许更新 Markdown 错题卡: {card}")

    wrongbook_root = None
    for parent in card.parents:
        if parent.name == "错题本":
            wrongbook_root = parent
            break
    if wrongbook_root is None:
        json_error(f"卡片路径必须位于错题本目录下: {card}")

    vault_root = wrongbook_root.parent
    if not ((vault_root / "知识地图").exists() or (vault_root / "我的学习者档案.md").exists()):
        json_error(f"卡片路径不在有效的 vault 目录下: {card}")

    return card, wrongbook_root


def main():
    parser = argparse.ArgumentParser(description="更新错题卡")
    parser.add_argument("card_path", help="错题卡文件路径")
    parser.add_argument("--status", required=True, choices=["不会", "半会", "会"], help="复习结果")
    parser.add_argument("--comment", default="", help="本次复习简评")
    parser.add_argument("--question-id", help="回填或校验 question_id")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args()

    try:
        card, wrongbook_root = resolve_card_path(args.card_path)
    except FileNotFoundError:
        json_error(f"文件不存在: {args.card_path}")

    text = card.read_text(encoding="utf-8")
    fm, body, key_order = parse_frontmatter(text)
    target_card = card

    today_obj = parse_today(args.today)
    today = today_obj.isoformat()
    old_interval = safe_int(fm.get("review_interval", 1))
    old_count = safe_int(fm.get("wrong_count", 0), 0)
    old_ease = safe_float(fm.get("ease_factor", "2.5"))

    # 更新基础字段
    fm["status"] = args.status
    fm["last_review_at"] = today
    if args.status == "不会":
        fm["wrong_count"] = str(old_count + 1)

    if args.question_id:
        if not QUESTION_ID_RE.match(args.question_id):
            json_error(f"question_id 格式非法: {args.question_id}")
        existing_qid = fm.get("question_id", "").strip()
        if existing_qid and existing_qid != args.question_id:
            json_error(f"question_id 冲突: 现有={existing_qid}, 传入={args.question_id}")
        fm["question_id"] = args.question_id
        if "question_id" not in key_order:
            insert_at = key_order.index("source") + 1 if "source" in key_order else 0
            key_order.insert(insert_at, "question_id")
        target_card = canonicalize_card_path(card, args.question_id)
        if not is_within_root(target_card, wrongbook_root):
            json_error(f"规范化后的卡片路径越界: {target_card}")
        if target_card != card and target_card.exists():
            json_error(f"目标文件已存在: {target_card}")

    # SRS 算法：调整 interval 和 ease_factor
    if args.status == "不会":
        new_interval = 1
        new_ease = max(old_ease * 0.8, 1.3)
    elif args.status == "半会":
        new_interval = max(int(old_interval * 1.2), old_interval + 1)
        new_ease = old_ease
    else:  # 会
        new_interval = min(int(old_interval * old_ease), 90)
        new_ease = old_ease + 0.1

    fm["review_interval"] = str(new_interval)
    fm["ease_factor"] = f"{new_ease:.2f}"
    fm["next_review"] = (today_obj + timedelta(days=new_interval)).isoformat()

    # 确保 ease_factor 在 key_order 中
    if "ease_factor" not in key_order:
        insert_at = key_order.index("review_interval") + 1 if "review_interval" in key_order else len(key_order)
        key_order.insert(insert_at, "ease_factor")

    # 更新正文中的 #status/ tag
    for old_status in ("不会", "半会", "会"):
        body = body.replace(f"#status/{old_status}", f"#status/{args.status}")

    # 追加历史记录
    history_line = f"\n- {today} - {args.status} - {args.comment}"
    if "### 历史记录" in body:
        body = body.rstrip() + history_line + "\n"
    else:
        body = body.rstrip() + "\n\n### 历史记录" + history_line + "\n"

    serialized = serialize_frontmatter(fm, key_order, body)

    final_card = card
    renamed_from = None
    atomic_write(card, serialized)
    if target_card != card:
        card.rename(target_card)
        renamed_from = card.name
        final_card = target_card

    result = {
        "updated": final_card.name,
        "status": args.status,
        "interval": new_interval,
        "ease_factor": f"{new_ease:.2f}",
        "next_review": fm["next_review"],
    }
    if renamed_from:
        result["renamed_from"] = renamed_from
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
