"""周上下文只统计明确数据，兼容旧数据并保持 vault 只读。"""
import json
import re
from datetime import date

import pytest

from helpers import log_path, run_script
from breakthrough_ops import parse_breakthroughs
from get_weekly_context import build_weekly_context, daily_completion_rates, weekly_card_counts, weekly_papers, weekly_subject_hours
from test_score_sections import successful_score


START = date(2026, 10, 12)
END = date(2026, 10, 18)
PLAN = 'Day1：重做;Day2：变式;Day3：验收'


def run(name, args, env=None):
    rc, out, err = run_script(name, args, env)
    assert rc == 0, out + err
    return json.loads(out)


def make_breakthrough(root, timestamp='2026-10-12T09:00:00+08:00', item_id=None):
    args = ['create', str(root), '--goal', '二重积分验收', '--source', '测试卷', '--plan', PLAN,
            '--criteria', '5题对4题', '--timestamp', timestamp]
    if item_id:
        args += ['--id', item_id]
    return run('manage_breakthrough.py', args)['id']


def snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob('*') if path.is_file()}


def card(root, qid, first, history, last=None):
    path = root / '错题本' / '数学一' / '高等数学' / f'{qid}.md'
    path.write_text(f'---\nquestion_id: {qid}\nfirst_wrong_at: {first}\n'
                    f'last_review_at: {last or first}\nreview_interval: 30\n'
                    'next_review: 2026-01-01\n---\n### 历史记录\n' + history)
    return path


def test_daily_rates_all_seven_days_null_missing_empty_zero_and_fences(vault_root):
    folder = vault_root / '周计划'
    (folder / '_今日计划-2026-10-12.md').write_text(
        '# 今日计划：2026-10-12\n## 任务清单\n- [x] 完成\n- [ ] 未完成\n'
        '```text\n- [x] 示例不能计入\n```\n## 其他\n- [x] 不能计入\n')
    (folder / '_今日计划-2026-10-13.md').write_text('## 任务清单\n- [X] 全部完成\n')
    (folder / '_今日计划-2026-10-14.md').write_text('## 任务清单\n')
    (folder / '_今日计划.md').write_text('# 今日计划：2026-10-18\n## 任务清单\n- [x] 当前未归档不计入\n')
    assert daily_completion_rates(vault_root, START) == {
        '2026-10-12': 0.5, '2026-10-13': 1.0, '2026-10-14': 0.0,
        '2026-10-15': None, '2026-10-16': None, '2026-10-17': None, '2026-10-18': None,
    }


def test_week_papers_include_objective_section_and_exclude_outside_week(sample_archive, vault_root):
    successful_score(vault_root, section='整卷', total='110', extra=['--score-objective', '40', '--score-big', '70'])
    successful_score(vault_root, section='选填')
    rc, out, err = run_script('record_paper_score.py', [str(vault_root), '408', '--paper', '前周卷',
        '--paper-type', '模拟', '--total', '100', '--date', '2026-10-11'])
    assert rc == 0, out + err
    papers = weekly_papers(vault_root, START, END)
    assert len(papers) == 2
    assert {paper['section']: paper['total_score'] for paper in papers} == {'整卷': 110, '选填': 40}
    assert all(paper['subject'] == '数学一' and paper['date'] == '2026-10-12' for paper in papers)
    assert all(paper['modules']['objective']['score'] == 40 for paper in papers)


def test_new_and_reviewed_counts_are_unique_cards_excluding_initial(vault_root):
    created = card(vault_root, 'qid-000000000001', '2026-10-12',
                   '- 2026-10-12 - 不会 - 首次归档\n- 2026-10-13 - 会 - 复习\n- 2026-10-15 - 半会 - 复习\n')
    card(vault_root, 'qid-000000000002', '2026-10-14', '- 2026-10-14 - 不会 - 首次归档\n')
    card(vault_root, 'qid-000000000003', '2026-10-01',
         '- 2026-10-01 - 不会 - 首次归档\n- 2026-10-18 - 不会 - 复习\n- 2026-10-19 - 会 - 后周不计\n')
    card(vault_root, 'qid-000000000004', '2026-10-19', '- 2026-10-19 - 不会 - 首次归档\n')
    card(vault_root, 'qid-000000000005', '2026-09-01', '', last='2026-10-16')
    created.with_name('重复副本.md').write_bytes(created.read_bytes())
    assert weekly_card_counts(vault_root, START, END) == (2, 3)


def test_cli_smoke_three_logs_two_scores_one_breakthrough_and_read_only(sample_archive, vault_root):
    log_path(vault_root, '2026-10-12').write_text(
        '# Session: 2026-10-12\n## 今日概览\n- **时长**: 3h\n## 分科时长\n'
        '| 科目 | 时长 |\n|---|---|\n| 数学一 | 2h |\n| 408 | 1h |\n')
    log_path(vault_root, '2026-10-13').write_text(
        '---\nsubject_hours: {"数学一": 1.5, "英语": 0.5, "408": 2}\n---\n'
        '## 今日概览\n- **时长**: 4小时\n')
    log_path(vault_root, '2026-10-14').write_text(
        '## 今日概览\n- **时长**: 2h\n## 分科时长\n- 数学一: 1h\n- 政治: 30min\n')
    for day, tasks in [('2026-10-12', '- [x] 完成\n- [ ] 未完成'),
                       ('2026-10-13', '- [x] 完成'), ('2026-10-14', '- [ ] 未完成')]:
        (vault_root / '周计划' / f'_今日计划-{day}.md').write_text('## 任务清单\n' + tasks + '\n')
    successful_score(vault_root, section='整卷', total='110', extra=['--score-objective', '40', '--score-big', '70'])
    successful_score(vault_root, paper='2021真题', section='选填', total='40')
    item_id = make_breakthrough(vault_root)
    run('manage_breakthrough.py', ['update-status', str(vault_root), '--id', item_id, '--day', '2',
                                 '--timestamp', '2026-10-13T10:00:00+08:00'])
    run('manage_breakthrough.py', ['close', str(vault_root), '--id', item_id, '--result', '长期关注',
                                 '--timestamp', '2026-10-14T10:00:00+08:00'])
    run('manage_breakthrough.py', ['close', str(vault_root), '--id', item_id, '--result', '延期',
                                 '--timestamp', '2026-10-15T10:00:00+08:00'])
    run('manage_breakthrough.py', ['update-status', str(vault_root), '--id', item_id, '--day', '5',
                                 '--timestamp', '2026-10-16T10:00:00+08:00'])
    run('manage_breakthrough.py', ['close', str(vault_root), '--id', item_id, '--result', '已攻克',
                                 '--timestamp', '2026-10-17T10:00:00+08:00'])
    card(vault_root, 'qid-000000000001', '2026-10-12', '- 2026-10-12 - 不会 - 首次归档\n')
    card(vault_root, 'qid-000000000002', '2026-10-01',
         '- 2026-10-01 - 不会 - 首次归档\n- 2026-10-13 - 会 - 复习\n')
    card(vault_root, 'qid-000000000003', '2026-10-10', '', last='2026-10-14')
    before = snapshot(vault_root)
    result = run('get_weekly_context.py', [str(vault_root), '--week-start', '2026-10-12'])
    assert {'daily_completion_rates', 'papers', 'subject_hours', 'breakthroughs', 'new_cards', 'reviewed_cards'} <= result.keys()
    assert list(result['daily_completion_rates'].values()) == [0.5, 1.0, 0.0, None, None, None, None]
    assert len(result['papers']) == 2
    assert {paper['section']: paper['total_score'] for paper in result['papers']} == {'整卷': 110, '选填': 40}
    assert result['subject_hours'] == {'数学一': 4.5, '408': 3.0, '英语一': 0.5, '政治': 0.5}
    assert result['unallocated_hours'] == 0.5
    assert (result['new_cards'], result['reviewed_cards']) == (1, 2)
    assert len(result['breakthroughs']) == 1
    events = result['breakthroughs'][0]['events']
    assert [event['type'] for event in events] == ['created', 'advanced', 'closed', 'extended', 'advanced', 'closed']
    assert events[2]['result'] == '转长期关注' and events[-1]['result'] == '通过'
    assert events[3]['total_days'] == 5 and events[4]['day'] == 5
    assert snapshot(vault_root) == before
    assert result == run('get_weekly_context.py', [str(vault_root), '--week-start', '2026-10-12'])


def test_hours_do_not_infer_subject_from_topic_and_log_layout_deduplicates(vault_root):
    log_path(vault_root, '2026-10-12').write_text('## 今日概览\n- **主题**: 数学一二重积分\n- **时长**: 3h30min\n')
    (vault_root / '学习日志' / '2026-10-12.md').write_text('## 今日概览\n- **时长**: 99h\n')
    hours, unallocated, gaps = weekly_subject_hours(vault_root, START, END)
    assert hours == {'数学一': 0.0, '408': 0.0, '英语一': 0.0, '政治': 0.0}
    assert unallocated == 3.5 and len(gaps) == 1


def test_missing_total_hours_are_null_even_with_explicit_subjects(vault_root):
    log_path(vault_root, '2026-10-12').write_text('## 今日概览\n- **时长**: 2h\n')
    log_path(vault_root, '2026-10-13').write_text('---\nsubject_hours: {"数学一": 1}\n---\n## 今日概览\n- **主题**: 积分\n')
    result = build_weekly_context(vault_root, START)
    assert result['subject_hours'] is None and result['unallocated_hours'] is None
    assert any(gap.get('date') == '2026-10-13' for gap in result['data_gaps'])


def test_explicit_zero_hours_and_negative_difference_are_not_missing(vault_root):
    path = log_path(vault_root, '2026-10-12')
    path.write_text('## 今日概览\n- **时长**: 0h\n')
    result = build_weekly_context(vault_root, START)
    assert result['subject_hours'] is not None and result['unallocated_hours'] == 0
    path.write_text('## 今日概览\n- **时长**: 1h\n## 分科时长\n- 数学一: 2h\n')
    result = build_weekly_context(vault_root, START)
    assert result['subject_hours']['数学一'] == 2 and result['unallocated_hours'] == -1
    assert any('超过' in gap['reason'] for gap in result['data_gaps'])


def test_old_breakthrough_events_null_not_inferred_from_current_state(sample_archive, vault_root):
    item_id = make_breakthrough(vault_root)
    run('manage_breakthrough.py', ['close', str(vault_root), '--id', item_id, '--result', '已攻克',
                                 '--timestamp', '2026-10-15T10:00:00+08:00'])
    sample_archive.write_text(re.sub(r'^- 事件记录：.*\n?', '', sample_archive.read_text(), flags=re.M))
    before = snapshot(vault_root)
    result = build_weekly_context(vault_root, START)
    assert result['breakthroughs'] == [{'id': item_id, 'goal': '二重积分验收', 'events': None}]
    assert result['breakthrough_snapshots'][0]['status'] == '已攻克'
    assert any('不从创建日期' in gap['reason'] for gap in result['data_gaps'])
    assert snapshot(vault_root) == before


def test_events_use_shanghai_week_boundaries_and_retries_do_not_duplicate(sample_archive, vault_root):
    item_id = make_breakthrough(vault_root, '2026-10-11T20:00:00+00:00')  # 北京时间周一。
    assert make_breakthrough(vault_root, '2026-10-11T20:00:00+00:00', item_id) == item_id
    args = ['update-status', str(vault_root), '--id', item_id, '--day', '2', '--timestamp', '2026-10-18T18:00:00+00:00']
    run('manage_breakthrough.py', args)  # 北京时间已到下周一，不计入本周。
    run('manage_breakthrough.py', args)
    result = build_weekly_context(vault_root, START)
    assert [event['type'] for event in result['breakthroughs'][0]['events']] == ['created']
    assert len(parse_breakthroughs(sample_archive.read_text())[0]['events']) == 2


@pytest.mark.parametrize('closing_result,event_type,event_result', [
    ('未通过', 'closed', '未通过'), ('取消', 'cancelled', None), ('放弃', 'cancelled', None),
])
def test_failed_closing_and_cancellation_events(sample_archive, vault_root, closing_result, event_type, event_result):
    item_id = make_breakthrough(vault_root)
    args = ['close', str(vault_root), '--id', item_id, '--result', closing_result,
            '--timestamp', '2026-10-13T10:00:00+08:00']
    run('manage_breakthrough.py', args)
    run('manage_breakthrough.py', args)
    event = build_weekly_context(vault_root, START)['breakthroughs'][0]['events'][-1]
    assert event['type'] == event_type and event.get('result') == event_result
    assert len(parse_breakthroughs(sample_archive.read_text())[0]['events']) == 2


def test_empty_context_env_root_and_non_monday_rejection(vault_root):
    result = run('get_weekly_context.py', ['--week-start', '2026-10-12'], {'KAOYAN_OBSIDIAN_ROOT': str(vault_root)})
    assert result['subject_hours'] is None and result['unallocated_hours'] is None
    assert result['papers'] == result['breakthroughs'] == []
    assert result['new_cards'] == result['reviewed_cards'] == 0
    assert all(rate is None for rate in result['daily_completion_rates'].values())
    rc, out, _ = run_script('get_weekly_context.py', [str(vault_root), '--week-start', '2026-10-13'])
    assert rc == 1 and '周一' in json.loads(out)['message']
