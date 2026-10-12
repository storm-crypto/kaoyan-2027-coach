"""单入口聚合：七项候选数据 + 无决策的档案事实摘要。"""
import json
from datetime import date

from helpers import run_script
from manage_breakthrough import close, create
from test_build_daily_plan import make_clustered_due_cards, POOL_KEYS


def test_aggregate_valid_json_env_and_yesterday_snapshot(sample_archive, vault_root):
    make_clustered_due_cards(vault_root)
    target = vault_root / '周计划/_今日计划.md'
    previous = '# 今日计划：2026-10-11\n## 任务清单\n- [x] 数学\n- [ ] 408\n'
    target.write_text(previous)
    create(vault_root, '定积分80%', 'm05-01', 'Day1：重做;Day2：变式;Day3：/test', '5对4', today=date(2026, 10, 12))
    rc, out, err = run_script('get_plan_context.py', ['--today', '2026-10-12'], {'KAOYAN_OBSIDIAN_ROOT': str(vault_root)})
    assert rc == 0, err
    context = json.loads(out)
    assert set(context) == POOL_KEYS | {'archive_summary'}
    assert context['available_hours'] == 6
    assert context['due_clusters'][0]['due_count'] == 12
    assert context['breakthroughs'][0]['id'] == '突破单-20261012-01'
    assert context['yesterday_unfinished'] == ['408']
    assert context['yesterday_completion_rate'] == 0.5
    assert target.read_text() == previous
    assert (target.parent / '_今日计划-2026-10-11.md').read_text() == previous
    summary = context['archive_summary']
    assert summary['stage'] == '408重构期 / 数学提速期'
    assert summary['target_total'] == 360
    assert summary['subject_targets']['数学一'] == 125
    assert summary['exam_date'] == '2026-12-20'
    assert summary['next_steps'] == ['数学优先提速', '408 专题化复盘', '英语保持阅读节奏']
    assert 'priorities' not in summary and 'first_step' not in summary
    assert 'current_stage' not in summary
    rc, second, err = run_script('get_plan_context.py', [str(vault_root), '--today', '2026-10-12'])
    assert rc == 0, err
    assert json.loads(second) == context


def test_no_archive_and_closed_breakthrough_excluded(sample_archive, vault_root):
    item = create(vault_root, '换元', 'm05-01', 'Day1：重做', '标准', today=date(2026, 10, 12))
    close(vault_root, item['id'], '长期关注')
    rc, out, err = run_script('get_plan_context.py', [str(vault_root), '--today', '2026-10-12', '--available-hours', '4.12345'])
    assert rc == 0, err
    context = json.loads(out)
    assert context['available_hours'] == 4.12345
    assert context['breakthroughs'] == []
    assert context['yesterday_completion_rate'] is None
    assert context['yesterday_unfinished'] == []
    assert context['due_clusters'] == []
    assert context['textbook_progress'] == []


def test_archive_summary_uses_load_context_fact_builder(sample_archive, vault_root):
    from load_context import build_archive_summary
    rc, out, err = run_script('get_plan_context.py', [str(vault_root), '--today', '2026-10-12'])
    assert rc == 0, err
    assert json.loads(out)['archive_summary'] == build_archive_summary(vault_root, date(2026, 10, 12))
