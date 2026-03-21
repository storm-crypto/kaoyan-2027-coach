#!/usr/bin/env python3
"""更新错题卡的 YAML frontmatter 并追加历史记录。

用法: python3 update_card.py [卡片路径] --status [不会/半会/会] [--comment 简评] [--question-id QUESTION_ID]

自动处理:
- 更新 status, last_review_at, wrong_count, next_review, review_interval
- 根据 status 调整 review_interval（不会→1, 半会→不变, 会→×2 上限30）
- 在"### 历史记录"下追加一行
"""
import sys, argparse
from datetime import date, timedelta
from pathlib import Path


def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, "", ""
    end = text.find("---", 3)
    if end == -1:
        return {}, "", ""
    fm_text = text[3:end].strip()
    fm = {}
    key_order = []
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
        key_order.append(key)
    body = text[end + 3:]
    return fm, body, key_order


def serialize_frontmatter(fm, key_order, body):
    lines = ["---"]
    for k in key_order:
        if k not in fm:
            continue
        v = fm[k]
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(v)}]")
        else:
            lines.append(f"{k}: {v}")
    # any new keys not in original order
    for k, v in fm.items():
        if k not in key_order:
            if isinstance(v, list):
                lines.append(f"{k}: [{', '.join(v)}]")
            else:
                lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + body


def main():
    parser = argparse.ArgumentParser(description="更新错题卡")
    parser.add_argument("card_path", help="错题卡文件路径")
    parser.add_argument("--status", required=True, choices=["不会", "半会", "会"], help="复习结果")
    parser.add_argument("--comment", default="", help="本次复习简评")
    parser.add_argument("--question-id", help="回填或校验 question_id")
    args = parser.parse_args()

    card = Path(args.card_path)
    if not card.exists():
        print(f"错误: 文件不存在 {card}", file=sys.stderr)
        sys.exit(1)

    text = card.read_text(encoding="utf-8")
    fm, body, key_order = parse_frontmatter(text)

    today = date.today().isoformat()
    old_interval = int(fm.get("review_interval", 1))
    old_count = int(fm.get("wrong_count", 1))

    # 更新 status
    fm["status"] = args.status
    fm["last_review_at"] = today
    fm["wrong_count"] = str(old_count + 1)

    if args.question_id:
        existing_question_id = fm.get("question_id", "").strip()
        if existing_question_id and existing_question_id != args.question_id:
            print(
                f"错误: question_id 冲突，现有={existing_question_id}，传入={args.question_id}",
                file=sys.stderr,
            )
            sys.exit(1)
        fm["question_id"] = args.question_id
        if "question_id" not in key_order:
            insert_at = key_order.index("source") + 1 if "source" in key_order else 0
            key_order.insert(insert_at, "question_id")

    # 调整 interval
    if args.status == "不会":
        new_interval = 1
    elif args.status == "半会":
        new_interval = old_interval
    else:  # 会
        new_interval = min(old_interval * 2, 30)

    fm["review_interval"] = str(new_interval)
    fm["next_review"] = (date.today() + timedelta(days=new_interval)).isoformat()

    # 更新正文中的 #status/ tag
    body = body.replace(f"#status/不会", f"#status/{args.status}")
    body = body.replace(f"#status/半会", f"#status/{args.status}")
    body = body.replace(f"#status/会", f"#status/{args.status}")

    # 追加历史记录
    history_line = f"\n- {today} - {args.status} - {args.comment}"
    if "### 历史记录" in body:
        body = body.rstrip() + history_line + "\n"
    else:
        body = body.rstrip() + "\n\n### 历史记录" + history_line + "\n"

    card.write_text(serialize_frontmatter(fm, key_order, body), encoding="utf-8")
    print(f"已更新: {card.name} → status={args.status}, interval={new_interval}, next_review={fm['next_review']}")


if __name__ == "__main__":
    main()
