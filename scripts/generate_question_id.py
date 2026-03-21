#!/usr/bin/env python3
"""基于来源和题号/题干摘要生成稳定的 question_id。

用法: python3 generate_question_id.py [来源] [题号/题干摘要...]
例:   python3 generate_question_id.py 900题 "第 12 题 二重积分极坐标"
      python3 generate_question_id.py 1000题 "f(x,y)=... 求积分"

输出: JSON 对象，含 question_id、source、locator。
"""
import hashlib
import json
import sys
import unicodedata


def normalize(text):
    text = unicodedata.normalize("NFKC", text).strip().lower()
    return "".join(ch for ch in text if ch.isalnum())


def main():
    if len(sys.argv) < 3:
        print(
            "用法: python3 generate_question_id.py [来源] [题号/题干摘要...]",
            file=sys.stderr,
        )
        sys.exit(1)

    source = sys.argv[1].strip()
    locator = " ".join(sys.argv[2:]).strip()
    source_key = normalize(source)
    locator_key = normalize(locator)

    if not source_key or not locator_key:
        print("错误: 来源和题号/题干摘要不能为空", file=sys.stderr)
        sys.exit(1)

    digest = hashlib.sha1(f"{source_key}|{locator_key}".encode("utf-8")).hexdigest()[:12]
    question_id = f"qid-{digest}"

    print(
        json.dumps(
            {
                "question_id": question_id,
                "source": source,
                "locator": locator,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
