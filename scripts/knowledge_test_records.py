"""独立知识测试证据；与知识地图共存，便于一次原子写入。"""
import hashlib
import html
import json
import re
from datetime import date

from wrong_card_path_map import resolve_wrong_card_chapter

START = "<!-- kaoyan:knowledge-tests:start -->"
END = "<!-- kaoyan:knowledge-tests:end -->"
RECORD_RE = re.compile(r"^<!-- kaoyan:knowledge-test (.+) -->$", re.M)
RESULTS = {"不会", "半会", "会"}


def identify_topics(subject, rows):
    """优先规范章节 ID；旧地图以完整路径生成确定性标识，不猜测重名行。"""
    for row in rows:
        module = re.split(r"[（(]", row["module"], maxsplit=1)[0].strip()
        numbered = re.match(r"^\d+\.(\d+)\s+(.+)$", row["topic"])
        leaf = f"{int(numbered.group(1)):02d} {numbered.group(2)}" if numbered else row["topic"]
        resolution = resolve_wrong_card_chapter(
            subject, f"{module}/{row['chapter']}/{leaf}", strict=False
        )
        if not resolution.is_canonical:
            resolution = resolve_wrong_card_chapter(subject, row["topic"], strict=False)
        identity = [subject, module, row["chapter"], row["topic"]]
        digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:20]
        row["topic_id"] = resolution.chapter_id if resolution.is_canonical else "km-" + digest
    return rows


def select_topic(rows, topic_id):
    matches = [row for row in rows if row["topic_id"] == topic_id]
    if len(matches) != 1:
        raise ValueError(f"考点标识 {topic_id} 匹配 {len(matches)} 行，需先核对知识地图；未写入")
    return matches[0]


def read_test_records(text):
    """损坏记录必须显式报错，不能在下次记录时被当成空数据覆盖。"""
    if START not in text and END not in text:
        return []
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        raise ValueError("知识测试记录区块边界损坏，请先修复；未写入")
    block = text.split(START, 1)[1].split(END, 1)[0]
    records = []
    seen = set()
    for raw in RECORD_RE.findall(block):
        try:
            record = json.loads(raw)
            required = ("test_id", "subject", "topic_id", "topic",
                        "date", "question", "answer", "judgment", "result")
            if not isinstance(record, dict) or any(not isinstance(record.get(k), str) or not record[k].strip() for k in required):
                raise ValueError("测试记录缺少字段")
            if any(not isinstance(record.get(k), str) for k in ("module", "chapter")):
                raise ValueError("测试记录缺少目录字段")
            date.fromisoformat(record["date"])
            if type(record.get("hinted")) is not bool or record["result"] not in RESULTS:
                raise ValueError("测试记录判定格式错误")
            if record["hinted"] and record["result"] == "会":
                raise ValueError("提示后完成不能记为会")
            if record["test_id"] in seen:
                raise ValueError("重复测试 ID")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"知识测试记录损坏：{exc}；未写入") from exc
        seen.add(record["test_id"])
        records.append(record)
    if block.count("<!-- kaoyan:knowledge-test ") != len(records) or not records:
        raise ValueError("知识测试记录元数据缺失或损坏，请先修复；未写入")
    return records


def render_test_records(text, records):
    """可读记录和结构化元数据一起生成；用户题面中的管道不能被误读为地图行。"""
    def safe(value):
        # 题面在引用块里，竖线不会变成地图列；保留 LaTeX 的 |、<、>。
        # 仅转义公式外的 HTML，避免把公式改成 MathJax 无法解析的实体。
        pieces = re.split(r"((?<!\\)\$\$[\s\S]*?(?<!\\)\$\$|(?<!\\)\$[^$\n]+?(?<!\\)\$)", str(value))
        return "".join(piece if index % 2 else html.escape(piece, quote=False)
                       for index, piece in enumerate(pieces))

    lines = [START, "## 知识测试记录", "", "每次作答独立记录；测试结果与上方掌握度由同一次写入保存。", ""]
    for record in records:
        lines.extend([
            f"### {record['date']} · {safe(record['topic'])} · {record['result']}", "",
            f"- 测试 ID：{safe(record['test_id'])}",
            f"- 考点标识：{safe(record['topic_id'])}",
            f"- 作答条件：{'提示后完成' if record['hinted'] else '无提示作答'}", "",
        ])
        for key, title in [("question", "题目"), ("answer", "作答"), ("judgment", "判定依据")]:
            lines += [f"**{title}**", ""]
            lines += ["> " + line for line in safe(record[key]).splitlines()]
            lines.append("")
        encoded = json.dumps(record, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("|", "\\u007c")
        lines += [f"<!-- kaoyan:knowledge-test {encoded} -->", ""]
    lines.append(END)
    block = "\n".join(lines)
    if START in text:
        return text[:text.index(START)] + block + text[text.index(END) + len(END):]
    return text.rstrip() + "\n\n" + block + "\n"
