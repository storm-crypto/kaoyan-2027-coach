#!/usr/bin/env python3
"""记录一次知识测试，并与掌握度在同一知识地图文件中原子保存。"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from build_knowledge_test import SUBJECT_MAP, parse_knowledge_map
from env_util import atomic_write, json_error, resolve_obsidian_root
from knowledge_test_records import (
    RESULTS, identify_topics, read_test_records, render_test_records, select_topic,
)
from study_ops import parse_today
from update_knowledge_map import replace_mastery_row


def record_knowledge_test(root, subject, *, topic_id, test_id, question, answer,
                          judgment, hinted, result, test_date):
    canonical, filename = SUBJECT_MAP.get(subject, (None, None))
    if canonical is None:
        raise ValueError(f"未知科目：{subject}")
    if result not in RESULTS or type(hinted) is not bool:
        raise ValueError("测试结果或提示标记无效")
    if hinted and result == "会":
        raise ValueError("提示后完成最多记半会，不能记为会；未写入")
    values = dict(topic_id=topic_id, test_id=test_id, question=question,
                  answer=answer, judgment=judgment)
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        raise ValueError("考点、测试 ID、题目、作答和判定依据均不能为空；未写入")
    day = date.fromisoformat(str(test_date)).isoformat()
    path = Path(root) / "知识地图" / filename
    text = path.read_text(encoding="utf-8")
    records = read_test_records(text)
    row = select_topic(identify_topics(canonical, parse_knowledge_map(path, text=text)), topic_id)
    record = {
        "test_id": test_id, "subject": canonical, "topic_id": topic_id,
        "module": row["module"], "chapter": row["chapter"], "topic": row["topic"],
        "date": day, "question": question, "answer": answer, "judgment": judgment,
        "hinted": hinted, "result": result,
    }
    previous = next((item for item in records if item["test_id"] == test_id), None)
    if previous:
        if previous != record:
            raise ValueError("测试 ID 已用于不同作答；请保留原记录，新作答使用新的 test_id；未写入")
        return {"path": str(path), "record": record, "replayed": True,
                "mastery": row["mastery"], "mastery_updated": False}

    # 补录较早测试不能覆盖更晚的验证结果；同日多次作答按真实记录顺序更新。
    update_mastery = not any(item["topic_id"] == topic_id and item["date"] > day for item in records)
    updated = replace_mastery_row(text, row["line_no"], result, expected_topic=row["topic"]) if update_mastery else text
    updated = render_test_records(updated, records + [record])
    if path.read_text(encoding="utf-8") != text:
        raise ValueError("知识地图在记录期间已被修改，请重新读取后重试；未写入")
    atomic_write(path, updated)
    return {"path": str(path), "record": record, "replayed": False,
            "mastery": result if update_mastery else row["mastery"],
            "mastery_updated": update_mastery}


def main():
    raw = sys.argv[1:]
    root_arg = raw.pop(0) if raw and raw[0] not in SUBJECT_MAP and not raw[0].startswith("--") else None
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("subject", choices=list(SUBJECT_MAP))
    for name in ("topic-id", "test-id", "question", "answer", "judgment"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--hinted", choices=("yes", "no"), required=True)
    parser.add_argument("--result", choices=sorted(RESULTS), required=True)
    parser.add_argument("--today", help="作答日期 YYYY-MM-DD；补录较早日期不覆盖更晚结果")
    args = parser.parse_args(raw)
    try:
        result = record_knowledge_test(
            resolve_obsidian_root(root_arg), args.subject, topic_id=args.topic_id,
            test_id=args.test_id, question=args.question, answer=args.answer,
            judgment=args.judgment, hinted=args.hinted == "yes", result=args.result,
            test_date=parse_today(args.today),
        )
    except (OSError, ValueError) as exc:
        json_error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
