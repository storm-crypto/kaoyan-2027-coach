"""元技能浏览契约：主次归属、未知状态、只读与派生目录刷新。"""
from datetime import date
import json
from pathlib import Path

from helpers import run_script
from dashboard_payload import build_payload
from metaskill_browser import build_metaskills, render_metaskill_markdown
from metaskill_view import render_metaskills


def put_index(root, clusters):
    path = root / '错题本/_元技能索引.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'clusters': clusters}, ensure_ascii=False))
    return path


def cluster(cid, qids, also=()):
    return {'id': cid, 'name': '指示变量计数', 'ch': '概率论 ch4 数字特征',
            'skill': '看到总个数 → 写成指示变量之和', 'family': '指示变量',
            'qids': qids, 'also': list(also)}


def test_secondary_memberships_do_not_double_count_status_or_due(vault_root):
    put_index(vault_root, [cluster('m01-01', ['111111111111'], ['222222222222']),
                           cluster('m01-02', ['222222222222'])])
    cards = []
    for q, status, due in [('111111111111', '会', False), ('222222222222', '不会', True)]:
        cards.append({'question_id': 'qid-'+q, 'path': str(vault_root / f'错题本/数学一/概率论与数理统计/题-qid-{q}.md'),
                      'subject': '数学一', 'topic': '题目', 'status': status, 'is_due': due,
                      'chapter': '概率论', 'last_review_at': '2026-10-12', 'next_review': '2026-10-13'})
    data = build_metaskills(vault_root, cards, lambda *_: None)
    first = next(c for c in data['clusters'] if c['id'] == 'm01-01')
    assert first['counts'] == {'会': 1}
    assert first['due_count'] == 0
    assert first['members'][1]['role'] == '次归属'
    assert first['members'][1]['primary_clusters'] == ['m01-02']
    assert first['module'] == '概率统计'
    assert data['total_cards'] == 2


def test_missing_cards_and_unknown_status_remain_visible(vault_root):
    put_index(vault_root, [cluster('m01-01', ['111111111111', '222222222222'])])
    card = {'question_id': 'qid-111111111111', 'path': str(vault_root / '错题本/数学一/概率论与数理统计/题.md'),
            'subject': '数学一', 'topic': '题', 'status': '', 'is_due': False,
            'chapter': '概率论', 'last_review_at': '-', 'next_review': '-'}
    data = build_metaskills(vault_root, [card], lambda *_: None)
    assert data['clusters'][0]['counts'] == {'未标注': 1}
    assert data['clusters'][0]['members'][1]['missing']
    assert data['warnings']
    assert data['total_cards'] == 1


def test_derived_markdown_updates_without_changing_sources(sample_archive, sample_card, vault_root):
    path = put_index(vault_root, [cluster('m01-01', ['f728c5b18974'])])
    before = {p: p.read_bytes() for p in [path, sample_card, vault_root / '我的学习者档案.md']}
    args = [str(vault_root), '--today', '2026-10-13']
    rc, out, err = run_script('build_dashboard.py', args)
    assert rc == 0, err
    md = vault_root / '错题本/元技能目录.md'
    assert '主归属' in md.read_text()
    assert sample_card.stem in md.read_text()
    original = md.read_bytes()
    rc, _, err = run_script('build_dashboard.py', args)
    assert rc == 0, err
    assert md.read_bytes() == original
    assert before == {p: p.read_bytes() for p in before}
    data = json.loads(path.read_text())
    data['clusters'][0]['name'] = '新名称'
    path.write_text(json.dumps(data, ensure_ascii=False))
    rc, _, err = run_script('build_dashboard.py', args)
    assert rc == 0, err
    assert '新名称' in md.read_text() and '新名称' in (vault_root / '可视化面板/index.html').read_text()


def test_unclustered_and_malformed_index_do_not_disappear(sample_archive, sample_card, vault_root):
    path = put_index(vault_root, [])
    data = build_payload(vault_root, date(2026, 10, 13))['workbench']['metaskills']
    assert data['unclustered'][0]['qid'] == 'f728c5b18974'
    md = vault_root / '错题本/元技能目录.md'
    md.write_text('保留已有目录')
    path.write_text('{broken')
    rc, out, err = run_script('build_dashboard.py', [str(vault_root), '--today', '2026-10-13'])
    assert rc == 0, err
    assert md.read_text() == '保留已有目录'
    assert json.loads(out)['workbench']['metaskills']['warnings']


def test_untrusted_index_strings_cannot_break_out_of_json_script(vault_root):
    attack = '</script><img src=x onerror=alert(1)>'
    put_index(vault_root, [{**cluster('m01-01', []), 'name': attack, 'skill': attack}])
    data = build_metaskills(vault_root, [], lambda *_: None)
    html = render_metaskills(data)
    assert attack not in html
    assert '\\u003c/script' in html
    assert attack in render_metaskill_markdown(data, '2026-10-13')
