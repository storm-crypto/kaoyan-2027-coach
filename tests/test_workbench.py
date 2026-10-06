"""工作台关键契约：只读、日期、状态保留、证据与安全渲染。"""
from datetime import date
import json
from urllib.parse import parse_qs, urlparse

from helpers import run_script
from daily_plan_state import parse_daily_plan, preserve_completed_tasks
from build_daily_plan import build_task_list
from dashboard_payload import build_payload
from workbench_view import render_workbench


def plan(day, tasks):
    return f"# 今日计划：{day}\n\n## 任务清单\n{tasks}\n\n## 收尾提醒\n收尾\n"


def test_same_day_replan_preserves_completed_task_and_result():
    before = plan('2026-10-06', '- [x] [数学一] 极限（1 小时）\n   - 实际 40 分钟，独立完成\n- [x] [408] 调度（1 小时）')
    new = plan('2026-10-06', '- [ ] [数学一] 极限（0.5 小时）\n- [ ] [英语一] 阅读（1 小时）')
    merged = preserve_completed_tasks(new, before)
    tasks = parse_daily_plan(merged)['tasks']
    assert [(t['title'], t['done']) for t in tasks] == [('极限', True), ('阅读', False), ('调度', True)]
    assert '实际 40 分钟，独立完成' in merged
    assert preserve_completed_tasks(merged, before) == merged
    tomorrow = new.replace('2026-10-06', '2026-10-07')
    assert preserve_completed_tasks(tomorrow, before) == tomorrow


def test_stale_plan_does_not_become_todays_work(sample_archive, vault_root):
    target = vault_root / '周计划' / '_今日计划.md'
    target.write_text(plan('2026-10-05', '- [ ] [数学一] 旧任务（1 小时）'))
    payload = build_payload(vault_root, date(2026, 10, 6))
    assert not payload['workbench']['plan']['current']
    assert payload['workbench']['plan']['pending'] == []
    assert payload['workbench']['warnings']
    target.write_text(plan('2026-10-06', '- [x] [数学一] 已完成（1 小时）\n- [ ] [408] 下一项（1 小时）'))
    payload = build_payload(vault_root, date(2026, 10, 6))
    assert payload['workbench']['plan']['done'] == 1
    assert payload['workbench']['plan']['pending'][0]['title'] == '下一项'


def test_build_is_read_only_and_preserves_unknown_and_evidence(sample_archive, sample_card, knowledge_map, vault_root):
    (vault_root / '.obsidian').mkdir()
    path = knowledge_map / '数学一.md'
    path.write_text(path.read_text().replace('|  05.5 二重积分 |  |  |  |', '|  05.5 二重积分 | 半会 |  | 1. [2026-03-15] 上下限混淆 (qid-f728c5b18974) |'))
    before = {p: p.read_bytes() for p in vault_root.rglob('*.md')}
    rc, out, err = run_script('build_dashboard.py', [str(vault_root), '--today', '2026-03-20'])
    assert rc == 0, err
    assert before == {p: p.read_bytes() for p in vault_root.rglob('*.md')}
    wb = json.loads(out)['workbench']
    topics = [t for s in wb['knowledge'] for c in s['chapters'] for t in c['topics']]
    assert sum(t['status'] == '待测' for t in topics) == 4
    known = next(t for t in topics if t['status'] == '半会')
    assert known['evidence'][0]['last_review'] == '2026-03-15'
    params = parse_qs(urlparse(known['evidence'][0]['link']['uri']).query)
    assert params['vault'] == [vault_root.name]
    assert params['file'][0].endswith(sample_card.stem)
    assert wb['reviews'][0]['cards'][0]['command'] == '/review qid-f728c5b18974'


def test_refresh_if_exists_does_not_create_empty_workbench(vault_root):
    rc, out, err = run_script('build_dashboard.py', [str(vault_root), '--if-exists'])
    assert rc == 0, err
    assert json.loads(out)['skipped']
    assert not (vault_root / '可视化面板').exists()


def test_html_escapes_note_content_and_does_not_embed_solutions(sample_archive, sample_card, knowledge_map, vault_root):
    attack = '<img src=x onerror="alert(1)">'
    path = knowledge_map / '数学一.md'
    path.write_text(path.read_text().replace('|  05.5 二重积分 |  |  |  |', f'|  05.5 二重积分 | 半会 |  | {attack} |'))
    payload = build_payload(vault_root, date(2026, 3, 20))
    rendered = render_workbench(payload, 'history.html')
    assert attack not in rendered
    assert '&lt;img' in rendered
    assert '先画积分区域，再确定角度范围' not in rendered


def test_complete_clusters_must_fit_review_budget():
    cards = [{'subject': '数学一', 'topic': f'题{i}', 'path': f'{i}.md'} for i in range(8)]
    group = {'cluster_id':'m01', 'skill':'示例', 'ch':'极限', 'min':120, 'due_count':8, 'cards':cards}
    tasks, selected, _ = build_task_list(1, [], cards, [group])
    assert len(selected) == 1  # 24 分钟预算只够一题，不能把整组挤进去。
    assert sum(t['hours'] for t in tasks) <= 1
    assert '抽样诊断' in tasks[0]['detail']


def test_unknown_status_is_not_rewritten_as_failure(knowledge_map, vault_root):
    rc, out, err = run_script('build_knowledge_test.py', [str(vault_root), '数学一', '--count', '3'])
    assert rc == 0, err
    assert all(q['source_mastery'] == '待测' for q in json.loads(out)['questions'])
