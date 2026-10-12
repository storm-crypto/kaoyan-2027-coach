"""候选池只提供事实数据，不排序、抽样、分预算或生成计划正文。"""
from datetime import date
import json

from helpers import run_script
from textbook_progress import week_plan_path

POOL_KEYS = {
    'due_clusters', 'breakthroughs', 'yesterday_unfinished', 'yesterday_completion_rate',
    'focus_items', 'textbook_progress', 'available_hours',
}


def make_clustered_due_cards(root, count=12):
    folder = root / '错题本/数学一/高等数学'
    qids = []
    for i in range(count):
        qid = f'{i:012x}'
        qids.append(qid)
        (folder / f'例题-qid-{qid}.md').write_text(f'''---
source: test
question_id: qid-{qid}
topic: 定积分换元
status: 半会
next_review: 2026-10-12
review_interval: 2
---
### 题目
求积分 $\\int_0^1 x\\,dx$。
''', encoding='utf-8')
    index = {'clusters': [
        {'id': 'm05-01', 'skill': '定积分换元', 'ch': '定积分', 'min': 120, 'qids': qids},
    ]}
    (root / '错题本/_元技能索引.json').write_text(json.dumps(index, ensure_ascii=False))


def test_candidate_pool_passes_entire_scan_result(sample_archive, vault_root):
    make_clustered_due_cards(vault_root)
    rc, out, err = run_script('scan_due_reviews.py', [str(vault_root), '--today', '2026-10-12', '--by-cluster'])
    assert rc == 0, err
    expected = json.loads(out)['clusters']
    rc, out, err = run_script('build_daily_plan.py', [str(vault_root), '0.125123', '--today', '2026-10-12'])
    assert rc == 0, err
    pool = json.loads(out)
    assert set(pool) == POOL_KEYS
    assert pool['available_hours'] == 0.125123
    assert pool['due_clusters'] == expected
    assert pool['due_clusters'][0]['due_count'] == 12
    assert len(pool['due_clusters'][0]['cards']) == 12
    assert 'question_text' in pool['due_clusters'][0]['cards'][0]
    assert pool['yesterday_completion_rate'] is None
    assert pool['yesterday_unfinished'] == []
    assert pool['focus_items'] == ['数学二重积分和极坐标切换总卡', '408 操作系统调度和死锁题反复错', '英语阅读定位速度偏慢']


def test_write_only_saves_candidate_json(sample_archive, vault_root):
    target = vault_root / '周计划/_今日计划.md'
    target.write_text('AI 原来写的计划')
    rc, out, err = run_script('build_daily_plan.py', [str(vault_root), '4', '--today', '2026-10-12', '--write'])
    assert rc == 0, err
    saved = vault_root / '周计划/_候选池-2026-10-12.json'
    assert json.loads(saved.read_text()) == json.loads(out)
    assert target.read_text() == 'AI 原来写的计划'
    assert not list(target.parent.glob('_今日计划-*.md'))


def test_without_write_does_not_create_plan_or_debug_file(sample_archive, vault_root):
    rc, out, err = run_script('build_daily_plan.py', [str(vault_root), '4', '--today', '2026-10-12'])
    assert rc == 0, err
    assert set(json.loads(out)) == POOL_KEYS
    assert not list((vault_root / '周计划').iterdir())


def test_raw_textbook_rows_and_yesterday_unfinished(sample_archive, vault_root):
    week_plan_path(vault_root, date(2026, 10, 12)).write_text('''# 周计划
## 本周教材进度目标
| 教材 | 起点 | 终点 | 当前 | 备注 |
|------|------|------|------|------|
| 讲义 | p118 | p122 | p120 | 例题独立做 |
| 老汤408 | 第2节 | 第4节 | 第3节 | 不按页数计算 |
''')
    (vault_root / '周计划/_今日计划-2026-10-11.md').write_text('## 任务清单\n- [x] 完成\n- [ ] 整簇重做\n')
    rc, out, err = run_script('build_daily_plan.py', [str(vault_root), '--today', '2026-10-12'])
    assert rc == 0, err
    pool = json.loads(out)
    assert pool['available_hours'] == 6
    assert pool['yesterday_completion_rate'] == 0.5
    assert pool['yesterday_unfinished'] == ['整簇重做']
    assert pool['textbook_progress'] == [
        {'name': '讲义', 'start': 'p118', 'end': 'p122', 'current': 'p120', 'note': '例题独立做'},
        {'name': '老汤408', 'start': '第2节', 'end': '第4节', 'current': '第3节', 'note': '不按页数计算'},
    ]


def test_missing_index_passes_empty_clusters_no_fallback(sample_archive, sample_card, vault_root):
    rc, out, err = run_script('build_daily_plan.py', [str(vault_root), '--today', '2026-03-23'])
    assert rc == 0, err
    assert json.loads(out)['due_clusters'] == []


def test_hours_env_and_validation(sample_archive, vault_root):
    rc, out, err = run_script('build_daily_plan.py', ['2.34567', '--today', '2026-10-12'], {'KAOYAN_OBSIDIAN_ROOT': str(vault_root)})
    assert rc == 0, err
    assert json.loads(out)['available_hours'] == 2.34567
    for invalid in ('0', '-1', 'nan', 'inf', 'abc'):
        rc, out, _ = run_script('build_daily_plan.py', [str(vault_root), invalid])
        assert rc != 0
        assert json.loads(out)['error'] is True
