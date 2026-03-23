#!/usr/bin/env python3
"""基于知识地图生成知识测试题单。"""
import argparse
import json
import re
import sys
from pathlib import Path

from archive_ops import load_template_markdown
from env_util import json_error, resolve_obsidian_root

SUBJECT_MAP = {
    "数学一": ("数学一", "数学一.md"),
    "数学": ("数学一", "数学一.md"),
    "408": ("408", "408.md"),
    "政治": ("政治", "政治.md"),
    "英语一": ("英语一", "英语一.md"),
    "英语": ("英语一", "英语一.md"),
}

QUESTION_BLUEPRINTS = {
    "数学一": [
        {
            "type": "突破口识别",
            "prompt": "围绕“{topic}”，先说看到这类题时第一步该检查什么，再说明为什么优先从这里入手。",
            "checkpoints": ["能指出关键条件", "能说出优先方法/定理", "能说明为什么先不走常见错误路径"],
        },
        {
            "type": "核心方法",
            "prompt": "不用展开完整计算，概括“{topic}”最核心的判定依据或解题框架。",
            "checkpoints": ["结论方向正确", "能点出方法适用条件", "没有把相近方法混用"],
        },
        {
            "type": "易错点复盘",
            "prompt": "说出“{topic}”最容易错的一步，以及你会怎么在考场上自查。",
            "checkpoints": ["能说出具体坑点", "自查动作可执行", "能把错因落到条件/步骤"],
        },
        {
            "type": "变式判断",
            "prompt": "如果题目的一个关键条件被改掉，“{topic}”原方法还成不成立？简要说明理由。",
            "checkpoints": ["能识别关键条件", "能判断方法是否失效", "能说清变化原因"],
        },
        {
            "type": "做题口令",
            "prompt": "把“{topic}”压缩成一句做题口令：先看什么，再想什么，最后防什么。",
            "checkpoints": ["口令有顺序", "能覆盖方法触发点", "能包含一个避坑提醒"],
        },
    ],
    "408": [
        {
            "type": "判断轴",
            "prompt": "围绕“{topic}”，先说这类题最核心的判断轴是什么。",
            "checkpoints": ["能指出核心概念边界", "没有把层次混掉", "能说明判断时先看什么"],
        },
        {
            "type": "概念辨析",
            "prompt": "说清“{topic}”最容易和哪个相近概念混淆，并说明两者边界。",
            "checkpoints": ["能指出易混概念", "边界表述准确", "不是只背定义不解释"],
        },
        {
            "type": "条件变式",
            "prompt": "如果删掉一个关键条件，“{topic}”对应结论会不会变？为什么？",
            "checkpoints": ["能识别关键条件", "能判断结论是否改变", "理由不偷换概念"],
        },
        {
            "type": "干扰项排错",
            "prompt": "给“{topic}”举一个常见干扰项思路，并说明它为什么错。",
            "checkpoints": ["干扰项贴近考点", "能明确指出错因", "能落到具体概念"],
        },
        {
            "type": "知识串联",
            "prompt": "把“{topic}”挂回 408 知识网络里，再说一个经常和它一起考的点。",
            "checkpoints": ["能说出所属模块", "能串到相邻考点", "串联关系合理"],
        },
    ],
    "政治": [
        {
            "type": "概念界定",
            "prompt": "围绕“{topic}”，先用一句话界定它最核心的概念或原理。",
            "checkpoints": ["表述不跑题", "抓住关键词", "没有把价值判断和事实判断混掉"],
        },
        {
            "type": "易混对比",
            "prompt": "说出“{topic}”最容易和哪一组概念混淆，并做一个简短对比。",
            "checkpoints": ["能说出对比对象", "差异点明确", "记忆锚点清楚"],
        },
        {
            "type": "判断依据",
            "prompt": "如果把材料换一种说法，你判断“{topic}”时最先抓哪个关键词？",
            "checkpoints": ["能说出判断关键词", "能解释为什么抓它", "不是只给结论"],
        },
        {
            "type": "设坑识别",
            "prompt": "给“{topic}”说一个常见设坑点，并解释为什么容易被带偏。",
            "checkpoints": ["设坑点具体", "能指出混淆来源", "能给出识别方法"],
        },
        {
            "type": "记忆锚点",
            "prompt": "给“{topic}”提炼一个最适合考场回忆的记忆锚点。",
            "checkpoints": ["锚点简短", "能帮助区分易混点", "不失真"],
        },
    ],
    "英语一": [
        {
            "type": "定位信号",
            "prompt": "围绕“{topic}”，说这类题最先抓什么定位信号。",
            "checkpoints": ["能说出定位依据", "不是泛泛说看原文", "能点出优先顺序"],
        },
        {
            "type": "同义替换",
            "prompt": "给“{topic}”说一个常见同义替换或改写信号。",
            "checkpoints": ["替换方向合理", "能说明为什么算对应", "没有脱离语境"],
        },
        {
            "type": "干扰项识别",
            "prompt": "说一个“{topic}”里最常见的干扰项类型，并说明怎么排除。",
            "checkpoints": ["干扰类型明确", "排除依据具体", "能落到主语/范围/因果等层面"],
        },
        {
            "type": "长难句拆解",
            "prompt": "如果“{topic}”里遇到长难句，你会先拆哪一层结构？",
            "checkpoints": ["拆解顺序合理", "能抓主干", "能说明为什么这样拆"],
        },
        {
            "type": "解题口令",
            "prompt": "把“{topic}”压成一句解题口令：先找什么，再核对什么，最后防什么坑。",
            "checkpoints": ["口令有顺序", "包含定位与核对", "包含一个干扰项提醒"],
        },
    ],
}


def parse_args():
    raw_args = sys.argv[1:]
    obsidian_root_arg = None
    if raw_args and raw_args[0] not in SUBJECT_MAP and not raw_args[0].startswith("--"):
        obsidian_root_arg = raw_args[0]
        raw_args = raw_args[1:]

    parser = argparse.ArgumentParser(description="生成知识测试题单")
    parser.add_argument("subject", help="科目，如 数学一 / 408 / 政治 / 英语一")
    parser.add_argument("--chapter", default="", help="章节/模块/考点关键词，可选")
    parser.add_argument("--count", type=int, default=5, help="题量，建议 3-5")
    args = parser.parse_args(raw_args)
    if args.count <= 0:
        json_error("题量必须大于 0")
    return obsidian_root_arg, args


def normalize_topic(text):
    return re.sub(r"\s+", " ", text.strip())


def normalize_mastery(text):
    value = (text or "").strip()
    if not value:
        return "不会"
    return value


def mastery_priority(text):
    mastery = normalize_mastery(text)
    if mastery == "不会":
        return 0
    if mastery == "半会":
        return 1
    return 2


def parse_knowledge_map(path):
    rows = []
    current_module = ""
    current_chapter = ""

    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("## "):
            current_module = stripped[3:].strip()
            continue
        if "|" not in line:
            continue

        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) != 4:
            continue
        topic = normalize_topic(cells[0])
        if not topic or topic == "考点" or set(topic) == {"-"}:
            continue
        if topic.startswith("**") and topic.endswith("**"):
            current_chapter = topic.strip("*").strip()
            continue

        rows.append({
            "line_no": line_no,
            "module": current_module,
            "chapter": current_chapter,
            "topic": topic,
            "mastery": normalize_mastery(cells[1]),
            "note": cells[3].strip(),
        })
    return rows


def matches_filter(item, chapter_filter):
    if not chapter_filter:
        return True
    haystack = " ".join([item["module"], item["chapter"], item["topic"]]).lower()
    return all(token in haystack for token in chapter_filter.lower().split())


def build_question(item, subject, index):
    blueprint = QUESTION_BLUEPRINTS[subject][index % len(QUESTION_BLUEPRINTS[subject])]
    return {
        "index": index + 1,
        "question_type": blueprint["type"],
        "module": item["module"],
        "chapter": item["chapter"],
        "topic": item["topic"],
        "source_mastery": item["mastery"],
        "note": item["note"],
        "prompt": blueprint["prompt"].format(topic=item["topic"]),
        "checkpoints": blueprint["checkpoints"],
    }


def render_questions(questions):
    lines = []
    for question in questions:
        lines.append(f"{question['index']}. [{question['question_type']}] {question['prompt']}")
        lines.append(f"   - 考点：{question['topic']}")
        lines.append(f"   - 来源：{question['module']} / {question['chapter']}")
        lines.append(f"   - 当前掌握度：{question['source_mastery']}")
        lines.append(f"   - 判定要点：{'；'.join(question['checkpoints'])}")
        if question["note"]:
            lines.append(f"   - 现有备注：{question['note']}")
    return "\n".join(lines)


def render_markdown(subject, chapter_filter, questions):
    scope = chapter_filter or "当前科目全范围"
    grading_notes = "\n".join([
        "- 明显答不上来、判断轴错位，记为“不会”。",
        "- 结论方向对但解释不完整、条件没说清，记为“半会”。",
        "- 结论准确、条件清楚、变式也能说明白，记为“会”。",
        "- 判完后只回写知识地图，不新建错题卡。",
    ])
    content = load_template_markdown("知识测试模板.md")
    replacements = {
        "subject": subject,
        "scope": scope,
        "question_count": str(len(questions)),
        "questions": render_questions(questions),
        "grading_notes": grading_notes,
    }
    for key, value in replacements.items():
        content = content.replace(f"{{{key}}}", value)
    return content + "\n"


def main():
    obsidian_root_arg, args = parse_args()
    canonical_subject, filename = SUBJECT_MAP.get(args.subject, (None, None))
    if not canonical_subject:
        json_error(f"未知科目 '{args.subject}'")

    knowledge_map_path = resolve_obsidian_root(obsidian_root_arg) / "知识地图" / filename
    if not knowledge_map_path.exists():
        json_error(f"知识地图不存在: {knowledge_map_path}")

    rows = parse_knowledge_map(knowledge_map_path)
    candidates = [
        row for row in rows
        if mastery_priority(row["mastery"]) < 2 and matches_filter(row, args.chapter)
    ]
    candidates.sort(key=lambda item: (mastery_priority(item["mastery"]), item["line_no"]))

    if not candidates:
        scope = args.chapter or canonical_subject
        json_error(f"在 {scope} 范围内未找到“不会/半会”的叶子考点")

    selected = candidates[:args.count]
    questions = [build_question(item, canonical_subject, index) for index, item in enumerate(selected)]

    print(json.dumps({
        "subject": canonical_subject,
        "chapter_filter": args.chapter or None,
        "knowledge_map_path": str(knowledge_map_path),
        "candidate_total": len(candidates),
        "question_count": len(questions),
        "selection_rule": "优先选择掌握度为空/不会的叶子考点，再选择半会考点",
        "questions": questions,
        "markdown": render_markdown(canonical_subject, args.chapter, questions),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
