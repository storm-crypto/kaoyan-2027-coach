#!/usr/bin/env python3
"""突破单 Markdown CRUD；触发、目标和疗程内容由 AI 调用方决定。"""
import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

from breakthrough_ops import (
    DAY_RE, ensure_section, entry_span, parse_breakthroughs, replace_entry,
    section_span, set_field, set_status,
)
from env_util import atomic_write, json_error, resolve_obsidian_root
from study_ops import parse_today


def single_line(value: str, label: str, required: bool = True) -> str:
    value = value.strip()
    if (required and not value) or '\n' in value or '\r' in value:
        raise ValueError(f"{label}必须是{'非空' if required else ''}单行文本")
    return value


def parse_plan(value: str) -> list:
    plan = [part.strip() for part in re.split('[;；]', value) if part.strip()]
    if not plan:
        raise ValueError("疗程不能为空")
    for number, line in enumerate(plan, 1):
        single_line(line, "疗程")
        match = DAY_RE.fullmatch(line)
        if not match or int(match.group(1)) != number or not match.group(3).strip():
            raise ValueError("疗程须从 Day1 开始连续编号，格式为 Day1：内容;Day2：内容")
    return plan


def load(root: Path):
    path = Path(root) / "我的学习者档案.md"
    text = path.read_text(encoding="utf-8")
    return path, text, parse_breakthroughs(text)


def ensure_capacity(items: list, item_id: str = '') -> None:
    if sum(item['status'] == '进行中' and item['id'] != item_id for item in items) >= 3:
        raise ValueError("进行中的突破单已达到 3 个，请由 AI 决定排队")


def get_item(items: list, item_id: str) -> dict:
    for item in items:
        if item['id'] == item_id:
            return item
    raise ValueError(f"未找到突破单：{item_id}")


def create(root: Path, goal: str, source: str, plan: str, criteria: str,
           item_id: str = None, today: date = None, topic_ids=None) -> dict:
    path, text, items = load(root)
    today = today or date.today()
    topic_ids = list(dict.fromkeys(single_line(value, '考点id') for value in topic_ids or []))
    if item_id:
        if not re.fullmatch(r"突破单-\d{8}-\d{2,}", item_id):
            raise ValueError("id 格式须为 突破单-YYYYMMDD-NN")
        date.fromisoformat(f"{item_id[4:8]}-{item_id[8:10]}-{item_id[10:12]}")
        for item in items:
            if item['id'] == item_id:
                return {"id": item_id, "created": False}
    goal = single_line(goal, '目标')
    source = single_line(source, '来源')
    criteria = single_line(criteria, '验收标准')
    days = parse_plan(plan)
    signature_fields = [today.isoformat(), goal, source, days, criteria]
    if topic_ids:
        signature_fields.append(topic_ids)
    signature = hashlib.sha256(json.dumps(signature_fields, ensure_ascii=False).encode()).hexdigest()[:16]
    create_marker = f'<!-- breakthrough-create:{signature} -->'
    if not item_id:
        # 标记原始请求，疗程后来延期也不会让 create 重试产生新条目。
        for item in items:
            start, end = entry_span(text, item['id'])
            if create_marker in text[start:end]:
                return {"id": item['id'], "created": False}
        # 手工条目没有执行标记时按原始字段匹配。
        for item in items:
            if (item['created_date'], item['goal'], item['source'], item['plan'], item['criteria']) == (
                    today.isoformat(), goal, source, days, criteria) and item['topic_ids'] == topic_ids:
                return {"id": item['id'], "created": False}
        prefix = f"突破单-{today.strftime('%Y%m%d')}-"
        numbers = [int(item['id'].rsplit('-', 1)[1]) for item in items if item['id'].startswith(prefix)]
        item_id = f"{prefix}{max(numbers, default=0) + 1:02d}"
    ensure_capacity(items)
    raw = '\n'.join([
        f"### 🔥 {item_id}（进行中）", f"- 目标：{goal}", f"- 来源：{source}",
        "- 疗程：", *(f"  - {line}" for line in days), f"- 验收标准：{criteria}",
        f"- 状态：进行中（Day1/共{len(days)}天）", f"- 创建日期：{today.isoformat()}",
        create_marker,
    ])
    if topic_ids:
        raw = set_field(raw, '考点IDs', json.dumps(topic_ids, ensure_ascii=False))
    text = ensure_section(text)
    _, end = section_span(text)
    text = text[:end].rstrip() + '\n\n' + raw + '\n\n' + text[end:]
    atomic_write(path, text)
    return {"id": item_id, "created": True}


def update_status(root: Path, item_id: str, day: int) -> dict:
    path, text, items = load(root)
    item = get_item(items, item_id)
    if item['status'] != '进行中':
        raise ValueError("只能推进进行中的突破单")
    if day < item['day'] or day > item['total_days'] or day < 1:
        raise ValueError(f"day 必须在当前 Day{item['day']} 与 Day{item['total_days']} 之间")
    if day != item['day']:
        start, end = entry_span(text, item_id)
        raw = set_status(text[start:end].rstrip(), '进行中', day, item['total_days'])
        atomic_write(path, replace_entry(text, item_id, raw))
    return {"id": item_id, "day": day}


def close(root: Path, item_id: str, result: str, note: str = '') -> dict:
    path, text, items = load(root)
    item = get_item(items, item_id)
    if result not in ('已攻克', '延期', '长期关注', '放弃'):
        raise ValueError("不支持的结果")
    note = single_line(note, '备注', required=False)
    start, end = entry_span(text, item_id)
    raw = text[start:end].rstrip()
    status = {'已攻克': '已攻克', '长期关注': '长期关注', '放弃': '已放弃', '延期': '进行中'}[result]
    total = item['total_days']
    if result == '延期':
        # 以当前 Day 和 note 标记请求；同一请求重试不再次延长。
        operation = hashlib.sha256(f"{item['day']}|{note}".encode()).hexdigest()[:16]
        marker = f"<!-- breakthrough-extension:{operation} -->"
        if marker in raw:
            return {"id": item_id, "status": item['status'], "total_days": total, "changed": False}
        ensure_capacity(items, item_id)
        contents = [part.strip() for part in re.split('[;；]', note) if part.strip()]
        if len(contents) == 2:
            contents = [DAY_RE.fullmatch(part).group(3) if DAY_RE.fullmatch(part) else part for part in contents]
        else:
            contents = [note or '待 AI 补充'] * 2
        plan_lines = list(re.finditer(r"^\s+- Day[^\n]+$", raw, re.M))
        if not plan_lines:
            raise ValueError("突破单缺少疗程，无法延期")
        insert_at = plan_lines[-1].end()
        addition = '\n' + '\n'.join(f"  - Day{total + i}：{content}" for i, content in enumerate(contents, 1))
        raw = raw[:insert_at] + addition + raw[insert_at:]
        total += 2
        raw = raw.rstrip() + '\n' + marker
    else:
        if item['status'] == status and (not note or item['note'] == note):
            return {"id": item_id, "status": status, "total_days": total, "changed": False}
        if note:
            raw = set_field(raw, '备注', note)
    raw = set_status(raw, status, item['day'], total)
    atomic_write(path, replace_entry(text, item_id, raw))
    return {"id": item_id, "status": status, "total_days": total, "changed": True}


def main() -> None:
    parser = argparse.ArgumentParser(description="管理突破单")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser('create')
    p.add_argument('obsidian_root', nargs='?')
    p.add_argument('--goal', required=True)
    p.add_argument('--source', required=True)
    p.add_argument('--plan', required=True)
    p.add_argument('--criteria', required=True)
    p.add_argument('--id')
    p.add_argument('--today', help='编号与创建日期 YYYY-MM-DD')
    p.add_argument('--topic-id', action='append', default=[], help='疗程叶子考点 chapter_id，可重复')
    p = sub.add_parser('update-status')
    p.add_argument('obsidian_root', nargs='?')
    p.add_argument('--id', required=True)
    p.add_argument('--day', required=True, type=int)
    p = sub.add_parser('close')
    p.add_argument('obsidian_root', nargs='?')
    p.add_argument('--id', required=True)
    p.add_argument('--result', choices=['已攻克', '延期', '长期关注', '放弃'], required=True)
    p.add_argument('--note', default='')
    argv = sys.argv[1:]
    # 同时支持 ROOT create 和 create ROOT；无 ROOT 时读环境变量。
    if len(argv) > 1 and argv[0] not in ('create', 'update-status', 'close') and not argv[0].startswith('-'):
        argv = [argv[1], argv[0], *argv[2:]]
    args = parser.parse_args(argv)
    try:
        root = resolve_obsidian_root(args.obsidian_root)
        if args.command == 'create':
            result = create(root, args.goal, args.source, args.plan, args.criteria, args.id,
                            parse_today(args.today), args.topic_id)
        elif args.command == 'update-status':
            result = update_status(root, args.id, args.day)
        else:
            result = close(root, args.id, args.result, args.note)
    except (ValueError, OSError) as exc:
        json_error(str(exc))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
