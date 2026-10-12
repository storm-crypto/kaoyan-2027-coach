#!/usr/bin/env python3
"""周级只读事实聚合；不排计划、不生成正文、不写入 vault。"""
import argparse
import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from archive_ops import extract_heading_block
from breakthrough_ops import parse_breakthroughs
from card_history import first_wrong_day, history_entries
from constants import PLAN_SUBJECTS
from duration_parser import parse_logged_hours
from env_util import json_error, resolve_obsidian_root
from frontmatter import parse_frontmatter
from log_layout import iter_log_files_in_range
from paper_analysis_lib import module_scores
from plan_ops import yesterday_completion_rate
from score_record_lib import SUBJECT_ALIASES, SUBJECT_SCORE_FIELDS, collect_score_records
from study_ops import iter_review_cards


def daily_completion_rates(root, start):
    return {
        (start + timedelta(days=offset)).isoformat(): yesterday_completion_rate(
            root, start + timedelta(days=offset + 1))[0]
        for offset in range(7)
    }


def weekly_papers(root, start, end):
    papers = []
    for record in collect_score_records(root, section=None):
        exam_day = date.fromisoformat(record['exam_date'])
        if not start <= exam_day <= end:
            continue
        modules = module_scores(record)
        if record['subject'] not in {'数学一', '408'}:
            modules = {
                field.removeprefix('score_'): {'score': record[field]}
                for field in SUBJECT_SCORE_FIELDS[record['subject']] if record.get(field) is not None
            }
        papers.append({
            'subject': record['subject'], 'paper': record['paper'], 'paper_type': record['paper_type'],
            'section': record['section'], 'total_score': record['total_score'],
            'modules': modules, 'date': record['exam_date'], 'record_path': record['path'],
        })
    return sorted(papers, key=lambda item: (item['date'], item['subject'], item['paper_type'], item['paper'], item['section']))


def weekly_card_counts(root, start, end):
    new = set()
    reviewed = set()
    for card in iter_review_cards(root):
        if card['icloud_placeholder']:
            continue
        fm = card['frontmatter']
        qid = str(fm.get('question_id') or card['path'])
        first = first_wrong_day(card)
        if first and first > end:
            continue
        if first and start <= first <= end:
            new.add(qid)
        entries = history_entries(card['body'])
        if entries and first and entries[0]['date'] == first:
            entries = entries[1:]  # 首次归档不计一次复习。
        if any(start <= entry['date'] <= end for entry in entries):
            reviewed.add(qid)
        else:
            # 历史缺记录时，明确的 last_review_at 可证明一次复习；创建当天无法区分。
            try:
                last = date.fromisoformat(str(fm.get('last_review_at', '')))
            except ValueError:
                continue
            if start <= last <= end and last != first:
                reviewed.add(qid)
    return len(new), len(reviewed)


def duration_hours(value):
    """只接受明确的数字小时或 h/小时/min/分钟组合。"""
    text = str(value).strip()
    if not re.fullmatch(r'(?:\d+(?:\.\d+)?\s*(?:h|小时|min|分钟)\s*)+|\d+(?:\.\d+)?', text, re.I):
        raise ValueError(f'无法解析明确时长：{text}')
    hours = parse_logged_hours(f'时长：{text}')
    if not math.isfinite(hours):
        raise ValueError('时长必须是有限数值')
    return hours


def unfenced(text):
    lines = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return '\n'.join(lines)


def logged_subject_hours(text):
    """优先 inline JSON frontmatter，再分科时长表/列表，最后时长字段的分科列举。"""
    fm, body, _ = parse_frontmatter(text)
    body = unfenced(body)
    totals = re.search(r'^\s*(?:-\s*)?(?:\*\*)?(?:总时长|全天时长|时长)(?:\*\*)?\s*[:：]\s*(.+)$', body, re.M)
    total_text = totals.group(1).strip() if totals else ''
    total = None
    if total_text:
        try:
            total = duration_hours(total_text)
        except ValueError:
            pass  # 分科列举不是全天总时长；不取其中第一个数当总时长。
    values = {}

    def add(subject, value):
        canonical = SUBJECT_ALIASES.get(subject.strip().strip('*'))
        if canonical:
            values[canonical] = values.get(canonical, 0.0) + duration_hours(value)

    if fm.get('subject_hours'):
        raw = json.loads(str(fm['subject_hours']))
        if not isinstance(raw, dict):
            raise ValueError('日志 subject_hours 须为 JSON 对象')
        for subject, hours in raw.items():
            add(subject, hours)
    else:
        block = extract_heading_block(body, '分科时长')
        if block:
            for line in block.splitlines():
                if line.lstrip().startswith('|'):
                    cells = [cell.strip() for cell in line.strip().split('|')[1:-1]]
                    if len(cells) == 2:
                        add(cells[0], cells[1])
                else:
                    match = re.match(r'^\s*-\s*([^:=：]+)\s*[:：=]\s*(.+)$', line)
                    if match:
                        add(match.group(1), match.group(2))
        elif total_text:
            for part in re.split(r'[;；,，]', total_text):
                match = re.fullmatch(r'\s*(数学一|数学|408|英语一|英语|政治)\s*[:：=]?\s*(.+?)\s*', part)
                if match:
                    add(match.group(1), match.group(2))
    return values, total


def weekly_subject_hours(root, start, end):
    hours = {subject: 0.0 for subject in PLAN_SUBJECTS}
    unallocated = 0.0
    gaps = []
    logs = list(iter_log_files_in_range(root, start, end))
    complete_totals = bool(logs)
    for day, path in logs:
        values, total = logged_subject_hours(path.read_text(encoding='utf-8'))
        for subject, value in values.items():
            hours[subject] += value
        allocated = sum(values.values())
        if total is not None:
            remainder = total - allocated
            unallocated += remainder  # 严格保留差值，不把冲突的负差值裁成零。
            if remainder > 1e-8:
                gaps.append({'source': str(path), 'date': day.isoformat(), 'reason': '部分或全部总时长未注明科目'})
            elif remainder < -1e-8:
                gaps.append({'source': str(path), 'date': day.isoformat(), 'reason': '分科时长之和超过日志总时长'})
        else:
            complete_totals = False
            gaps.append({'source': str(path), 'date': day.isoformat(), 'reason': '缺少日志总时长，周级时长无法完整汇总'})
    if not complete_totals:
        return None, None, gaps
    return {subject: round(value, 6) for subject, value in hours.items()}, round(unallocated, 6), gaps


def weekly_breakthroughs(root, start, end):
    path = root / '我的学习者档案.md'
    if not path.exists():
        return [], [], []
    # 不能用 load_archive_text：它可能迁移并回写档案。
    items = parse_breakthroughs(path.read_text(encoding='utf-8'))
    changes, snapshots, gaps = [], [], []
    event_types = {'created', 'advanced', 'extended', 'closed', 'cancelled'}
    for item in items:
        snapshots.append({key: item[key] for key in ('id', 'goal', 'status', 'day', 'total_days', 'created_date', 'topic_ids')})
        recorded = item['events']
        if not recorded:
            changes.append({'id': item['id'], 'goal': item['goal'], 'events': None})
            gaps.append({'source': str(path), 'id': item['id'], 'reason': '旧单无事件记录，本周变化未知；不从创建日期或当前状态反推'})
            continue
        if not any(event.get('type') == 'created' for event in recorded):
            gaps.append({'source': str(path), 'id': item['id'], 'reason': '旧单仅有部分事件记录，之前的变化未知'})
        seen = set()
        events = []
        for event in recorded:
            try:
                timestamp = event['timestamp']
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}', timestamp):
                    day = date.fromisoformat(timestamp)
                else:
                    moment = datetime.fromisoformat(timestamp)
                    if moment.tzinfo is None:
                        raise ValueError('timestamp 缺少时区')
                    day = moment.astimezone(ZoneInfo('Asia/Shanghai')).date()
            except (KeyError, TypeError, ValueError):
                gaps.append({'source': str(path), 'id': item['id'], 'reason': '事件 timestamp 缺失或无效'})
                continue
            if not isinstance(event.get('type'), str) or event['type'] not in event_types:
                gaps.append({'source': str(path), 'id': item['id'], 'reason': '未知突破单事件类型'})
                continue
            signature = json.dumps(event, ensure_ascii=False, sort_keys=True)
            if start <= day <= end and signature not in seen:
                events.append(event)
                seen.add(signature)
        if events:
            # 顺序沿用操作日志；日期精度的事件不编造排序时分。
            changes.append({'id': item['id'], 'goal': item['goal'], 'events': events})
    return changes, snapshots, gaps


def build_weekly_context(root, start):
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f'vault 根目录不存在：{root}')
    if start.weekday() != 0:
        raise ValueError('week-start 必须是周一日期')
    end = start + timedelta(days=6)
    hours, unallocated, hour_gaps = weekly_subject_hours(root, start, end)
    breakthroughs, snapshots, breakthrough_gaps = weekly_breakthroughs(root, start, end)
    new, reviewed = weekly_card_counts(root, start, end)
    result = {
        'week_start': start.isoformat(), 'week_end': end.isoformat(),
        'daily_completion_rates': daily_completion_rates(root, start),
        'papers': weekly_papers(root, start, end), 'subject_hours': hours, 'unallocated_hours': unallocated,
        'breakthroughs': breakthroughs, 'breakthrough_snapshots': snapshots,
        'new_cards': new, 'reviewed_cards': reviewed,
    }
    if hour_gaps or breakthrough_gaps:
        result['data_gaps'] = hour_gaps + breakthrough_gaps
    return result


def main():
    parser = argparse.ArgumentParser(description='输出只读周级学习事实 JSON')
    parser.add_argument('vault_root', nargs='?')
    parser.add_argument('--week-start', required=True, help='周一日期 YYYY-MM-DD')
    args = parser.parse_args()
    try:
        context = build_weekly_context(resolve_obsidian_root(args.vault_root), date.fromisoformat(args.week_start))
        payload = json.dumps(context, ensure_ascii=False, indent=2, allow_nan=False)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        json_error(str(exc))
    print(payload)


if __name__ == '__main__':
    main()
