"""突破单创建、推进、延期、关闭的幂等契约。"""
from datetime import date
import json

import pytest

from breakthrough_ops import parse_breakthroughs
from helpers import run_script
from manage_breakthrough import close, create, update_status

TODAY = date(2026, 10, 12)
PLAN = 'Day1（10-13）：m05-01 整簇重做 7 道;Day2（10-14）：变式 5 道;Day3（10-15）：/test 验收 5 道'


def make(root, item_id=None, goal='3 天内定积分换元正确率 ≥80%'):
    return create(root, goal, '2025 真题第 17/19 题 + 错题簇 m05-01', PLAN, '/test 5 道对 4 道', item_id, TODAY)


def read(path):
    return parse_breakthroughs(path.read_text())


def test_create_format_placement_and_same_id_noop(sample_archive, vault_root):
    sample_archive.write_text(sample_archive.read_text() + '\n## 其他信息\n保留这段\n')
    result = make(vault_root, '突破单-20261012-01')
    assert result == {'id': '突破单-20261012-01', 'created': True}
    text = sample_archive.read_text()
    assert text.index('## 下一步建议') < text.index('## 突破单') < text.index('## 其他信息')
    item = read(sample_archive)[0]
    assert item['status'] == '进行中' and item['day'] == 1 and item['total_days'] == 3
    assert item['created_date'] == TODAY.isoformat()
    assert item['plan'][0] == 'Day1（10-13）：m05-01 整簇重做 7 道'
    assert '### 🔥 突破单-20261012-01（进行中）' in text
    assert '- 状态：进行中（Day1/共3天）' in text
    assert not make(vault_root, '突破单-20261012-01', goal='不同目标')['created']
    assert sample_archive.read_text() == text


def test_auto_number_and_identical_auto_create_noop(sample_archive, vault_root):
    assert make(vault_root)['id'] == '突破单-20261012-01'
    original = sample_archive.read_bytes()
    assert not make(vault_root)['created']
    assert sample_archive.read_bytes() == original
    assert make(vault_root, goal='OS 调度')['id'] == '突破单-20261012-02'
    close(vault_root, '突破单-20261012-02', '已攻克')
    assert make(vault_root, '突破单-20261012-09', '阅读定位')['created']
    assert make(vault_root, goal='计网')['id'] == '突破单-20261012-10'


def test_fourth_active_rejected_and_retry_of_existing_allowed(sample_archive, vault_root):
    for n in range(1, 4):
        make(vault_root, f'突破单-20261012-0{n}', f'目标 {n}')
    before = sample_archive.read_bytes()
    rc, out, err = run_script('manage_breakthrough.py', ['create', str(vault_root), '--goal', '目标4', '--source', '错题簇', '--plan', PLAN, '--criteria', '5对4', '--id', '突破单-20261012-04'])
    assert rc != 0
    assert json.loads(out)['error']
    assert sample_archive.read_bytes() == before
    assert not make(vault_root, '突破单-20261012-01')['created']


def test_update_status_is_idempotent_and_only_advances(sample_archive, vault_root):
    make(vault_root)
    update_status(vault_root, '突破单-20261012-01', 2)
    before = sample_archive.read_bytes()
    assert read(sample_archive)[0]['day'] == 2
    update_status(vault_root, '突破单-20261012-01', 2)
    assert sample_archive.read_bytes() == before
    for invalid in (0, 1, 4):
        with pytest.raises(ValueError):
            update_status(vault_root, '突破单-20261012-01', invalid)
    close(vault_root, '突破单-20261012-01', '已攻克')
    with pytest.raises(ValueError):
        update_status(vault_root, '突破单-20261012-01', 3)


def test_extension_adds_two_days_and_retry_is_noop(sample_archive, vault_root):
    make(vault_root)
    update_status(vault_root, '突破单-20261012-01', 3)
    close(vault_root, '突破单-20261012-01', '延期', 'Day4：补强换元;Day5：复测')
    item = read(sample_archive)[0]
    assert item['status'] == '进行中' and item['total_days'] == 5 and item['day'] == 3
    assert item['plan'][-2:] == ['Day4：补强换元', 'Day5：复测']
    before = sample_archive.read_bytes()
    assert not close(vault_root, item['id'], '延期', 'Day4：补强换元;Day5：复测')['changed']
    assert sample_archive.read_bytes() == before
    update_status(vault_root, item['id'], 5)
    close(vault_root, item['id'], '延期')
    assert read(sample_archive)[0]['plan'][-2:] == ['Day6：待 AI 补充', 'Day7：待 AI 补充']


@pytest.mark.parametrize('result,status', [('已攻克', '已攻克'), ('长期关注', '长期关注'), ('放弃', '已放弃')])
def test_close_terminal_result_and_active_filter(sample_archive, vault_root, result, status):
    make(vault_root)
    close(vault_root, '突破单-20261012-01', result, '5 道对 4 道')
    assert read(sample_archive)[0]['status'] == status
    assert read(sample_archive)[0]['note'] == '5 道对 4 道'
    assert parse_breakthroughs(sample_archive.read_text(), active_only=True) == []
    before = sample_archive.read_bytes()
    assert not close(vault_root, '突破单-20261012-01', result, '5 道对 4 道')['changed']
    assert sample_archive.read_bytes() == before


def test_edit_preserves_other_entry_and_custom_lines(sample_archive, vault_root):
    make(vault_root)
    make(vault_root, '突破单-20261012-02', '调度')
    text = sample_archive.read_text().replace('- 来源：', '- 自定义证据：原样保留\n- 来源：', 1)
    sample_archive.write_text(text)
    untouched = text[text.index('### 🔥 突破单-20261012-02'):]
    update_status(vault_root, '突破单-20261012-01', 2)
    assert '自定义证据：原样保留' in sample_archive.read_text()
    assert sample_archive.read_text().endswith(untouched)


def test_delay_reactivation_obeys_capacity(sample_archive, vault_root):
    make(vault_root)
    close(vault_root, '突破单-20261012-01', '长期关注')
    for n in range(2, 5):
        make(vault_root, f'突破单-20261012-0{n}', str(n))
    before = sample_archive.read_bytes()
    with pytest.raises(ValueError):
        close(vault_root, '突破单-20261012-01', '延期')
    assert sample_archive.read_bytes() == before


def test_cli_env_and_root_before_command(sample_archive, vault_root):
    create_args = ['--goal', '定积分', '--source', 'm05-01', '--plan', PLAN, '--criteria', '5对4', '--today', '2026-10-12']
    rc, out, err = run_script('manage_breakthrough.py', ['create', *create_args], {'KAOYAN_OBSIDIAN_ROOT': str(vault_root)})
    assert rc == 0, err
    item_id = json.loads(out)['id']
    rc, out, err = run_script('manage_breakthrough.py', [str(vault_root), 'update-status', '--id', item_id, '--day', '2'])
    assert rc == 0, err
    assert json.loads(out)['day'] == 2
    rc, out, err = run_script('manage_breakthrough.py', ['close', '--id', item_id, '--result', '长期关注'], {'KAOYAN_OBSIDIAN_ROOT': str(vault_root)})
    assert rc == 0, err
    assert json.loads(out)['status'] == '长期关注'


@pytest.mark.parametrize('plan', ['', 'Day2：跳过1', 'Day1：;Day2：缺内容', 'Day1：a;Day3：不连续'])
def test_invalid_plan_does_not_mutate_archive(sample_archive, vault_root, plan):
    original = sample_archive.read_bytes()
    with pytest.raises(ValueError):
        create(vault_root, '目标', '来源', plan, '标准', today=TODAY)
    assert sample_archive.read_bytes() == original


def test_auto_create_retry_after_extension_keeps_original_id(sample_archive, vault_root):
    item_id = make(vault_root)['id']
    close(vault_root, item_id, '延期')
    before = sample_archive.read_bytes()
    assert make(vault_root) == {'id': item_id, 'created': False}
    assert sample_archive.read_bytes() == before
