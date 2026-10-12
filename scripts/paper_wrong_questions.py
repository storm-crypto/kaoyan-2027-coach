"""卷面错题的 JSON 落盘格式、参数校验及题号/日期范围查询。"""
import json
import re
from datetime import date


BLOCK_RE = re.compile(r'^## 卷子错题\s*\n+```json\s*\n(.*?)\n```', re.M | re.S)


def parse_numbered_values(value, subject, label):
    if value is None:
        return None
    if subject not in {"数学一", "408"}:
        raise ValueError(f"{label} 目前只支持数学一 / 408")
    limit = 22 if subject == "数学一" else 47
    result = {}
    if not value.strip():
        return result
    for entry in value.split(";"):
        number, separator, text = entry.partition(":")
        if not separator or not re.fullmatch(r"[0-9]+", number.strip()) or not text.strip():
            raise ValueError(f'{label} 格式应为 "题号:内容;题号:内容"，内容不能为空')
        number = int(number.strip())
        if not 1 <= number <= limit:
            raise ValueError(f"{subject} 题号必须在 1–{limit} 之间")
        if number in result:
            raise ValueError(f"{label} 题号重复: {number}")
        result[number] = text.strip()
    return result


def build_wrong_questions(value, topics, subject, record_date):
    errors = parse_numbered_values(value, subject, "wrong-questions")
    topic_map = parse_numbered_values(topics, subject, "question-topics") or {}
    if errors is None:
        if topic_map:
            raise ValueError("question-topics 需要同时传入 wrong-questions")
        return None  # 未传入时保留原有错题；空字符串显式清空。
    if topic_map.keys() - errors.keys():
        raise ValueError("question-topics 的题号必须出现在 wrong-questions 中")
    return [
        {"question_number": number, "error_description": text,
         "record_date": record_date, **({"topic": topic_map[number]} if number in topic_map else {})}
        for number, text in errors.items()
    ]


def render_wrong_questions(questions):
    # JSON 内反引号转义，防止用户文本意外关闭代码块。
    payload = json.dumps(questions, ensure_ascii=False, indent=2).replace("`", "\\u0060")
    return f"\n## 卷子错题\n\n```json\n{payload}\n```\n"


def parse_wrong_questions(body):
    match = BLOCK_RE.search(body)
    if not match:
        return []
    questions = json.loads(match.group(1))
    if not isinstance(questions, list):
        raise ValueError("卷子错题 JSON 必须为列表")
    for question in questions:
        if (not isinstance(question, dict)
                or type(question.get("question_number")) is not int
                or not isinstance(question.get("error_description"), str)):
            raise ValueError("卷子错题必须包含 question_number / error_description / record_date")
        date.fromisoformat(question["record_date"])
    return questions


def query_wrong_questions(records, question_number=None, start_date=None, end_date=None):
    """按卷面题号和闭区间日期查询，返回卷名、科目、路径及错题字段。"""
    result = []
    for record in records:
        for question in record.get("wrong_questions", []):
            day = date.fromisoformat(question["record_date"])
            if question_number is not None and question["question_number"] != question_number:
                continue
            if start_date is not None and day < start_date:
                continue
            if end_date is not None and day > end_date:
                continue
            result.append({**question, "paper": record["paper"], "subject": record["subject"],
                           "paper_type": record["paper_type"], "path": record["path"]})
    return result
