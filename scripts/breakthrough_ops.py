"""学习者档案中的突破单解析与局部写入；不决定目标、触发时机或疗程。"""
import re
from typing import List, Optional, Tuple

SECTION_RE = re.compile(r"^## 突破单[ \t]*\r?$", re.M)
ENTRY_RE = re.compile(r"^###\s+🔥\s*(突破单-\d{8}-\d+)\s*[（(]([^）)]+)[）)][ \t]*\r?$", re.M)
FIELD_RE = re.compile(r"^- (目标|来源|验收标准|状态|创建日期|备注)[：:]\s*(.*)$", re.M)
DAY_RE = re.compile(r"Day\s*(\d+)(?:[（(]([^）)]+)[）)])?[：:]\s*(.*)")


def section_span(text: str) -> Optional[Tuple[int, int]]:
    match = SECTION_RE.search(text)
    if not match:
        return None
    following = re.search(r"^#{1,2} ", text[match.end():], re.M)
    end = match.end() + following.start() if following else len(text)
    return match.end(), end


def parse_breakthroughs(text: str, active_only: bool = False) -> List[dict]:
    span = section_span(text)
    if span is None:
        return []
    block = text[span[0]:span[1]]
    headings = list(ENTRY_RE.finditer(block))
    items = []
    for heading in headings:
        tail = block[heading.end():]
        following = re.search(r"^### ", tail, re.M)
        end = heading.end() + following.start() if following else len(block)
        raw = block[heading.start():end].rstrip()
        fields = dict(FIELD_RE.findall(raw))
        status_text = fields.get("状态", heading.group(2)).strip()
        status = re.split(r"[（(]", status_text, maxsplit=1)[0].strip()
        progress = re.search(r"Day\s*(\d+)\s*/\s*共\s*(\d+)天", status_text)
        plan = []
        in_plan = False
        for line in raw.splitlines():
            if re.fullmatch(r"- 疗程[：:]\s*", line):
                in_plan = True
                continue
            if in_plan and line.startswith('- '):
                in_plan = False
            if in_plan:
                day = re.fullmatch(r"\s+-\s+(Day.+)", line)
                if day:
                    plan.append(day.group(1))
        item = {
            "id": heading.group(1), "goal": fields.get("目标", ""),
            "source": fields.get("来源", ""), "plan": plan,
            "criteria": fields.get("验收标准", ""), "status": status,
            "day": int(progress.group(1)) if progress else 1,
            "total_days": int(progress.group(2)) if progress else len(plan),
            "created_date": fields.get("创建日期", ""), "note": fields.get("备注", ""),
        }
        if not active_only or status == "进行中":
            items.append(item)
    return items


def entry_span(text: str, item_id: str) -> Tuple[int, int]:
    span = section_span(text)
    if span is not None:
        for match in ENTRY_RE.finditer(text, span[0], span[1]):
            if match.group(1) == item_id:
                following = re.search(r"^### ", text[match.end():span[1]], re.M)
                end = match.end() + following.start() if following else span[1]
                return match.start(), end
    raise ValueError(f"未找到突破单：{item_id}")


def ensure_section(text: str) -> str:
    if section_span(text) is not None:
        return text
    next_steps = re.search(r"^## 下一步建议[^\n]*", text, re.M)
    if next_steps:
        following = re.search(r"^#{1,2} ", text[next_steps.end():], re.M)
        position = next_steps.end() + following.start() if following else len(text)
    else:
        position = len(text)
    return text[:position].rstrip() + "\n\n## 突破单\n\n" + text[position:]


def set_field(raw: str, label: str, value: str) -> str:
    pattern = re.compile(rf"^- {re.escape(label)}[：:].*$", re.M)
    line = f"- {label}：{value}"
    if pattern.search(raw):
        return pattern.sub(lambda _: line, raw, count=1)
    return raw.rstrip() + "\n" + line


def set_status(raw: str, status: str, day: int, total: int) -> str:
    heading_status = status
    match = ENTRY_RE.search(raw)
    raw = raw[:match.start()] + f"### 🔥 {match.group(1)}（{heading_status}）" + raw[match.end():]
    display = f"进行中（Day{day}/共{total}天）" if status == "进行中" else status
    return set_field(raw, "状态", display)


def replace_entry(text: str, item_id: str, raw: str) -> str:
    start, end = entry_span(text, item_id)
    return text[:start] + raw.rstrip() + "\n\n" + text[end:]
