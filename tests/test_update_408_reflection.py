"""变式反馈是正文更新，不增加复习/错题，不破坏原题或统计。"""
from datetime import date
import json

from helpers import run_script
from archive_ops import extract_heading_block
from card_history import history_entries
from cs_card_layout import extract_module, heading_name, module_span
from dashboard_payload import collect_cards
from frontmatter import parse_frontmatter
from paper_card_links import associate_cards
from today_wrong_ops import extract_takeaway, scan_today_review_stats
from test_408_five_modules import make_card, VARIANT

TODAY = date(2026, 10, 20)
FEEDBACK = '结论正确，能区分进程状态变化与新建执行实体。\n\n- 2026-10-20 - 不会 - 这只是反馈中引用的例子，不是复习历史。'
MEMORY_ARGS = [
    '--memory-point', '操作系统：进程创建。',
    '--memory-trap', '把资源或状态变化误当成新建执行实体。',
    '--core-rule', '在本题语境下，只有新增执行实体才构成进程创建。',
    '--exam-action', '先检查进程实体是否增加，再判断资源和状态变化。',
]


def facts(root):
    return (collect_cards(root, TODAY), scan_today_review_stats(root, TODAY),
            associate_cards(root, '408', '2010年408真题', TODAY.isoformat()))


def test_feedback_and_final_summary_keep_yaml_history_prompt_links_and_statistics(vault_root):
    path = make_card(vault_root)
    original = path.read_text().replace('source:', '# 保留原始注释与字段顺序\nsource:', 1)
    original = original.replace('### 历史记录', '### 所属元技能\n\n- 原有入口\n\n### 相关题目\n\n- 原有题卡\n\n### 历史记录')
    path.write_text(original)
    before_fm, before_body, _ = parse_frontmatter(original)
    before_facts = facts(vault_root)
    rc, out, err = run_script('update_408_reflection.py', [str(path), '--feedback', FEEDBACK, *MEMORY_ARGS])
    assert rc == 0, out + err
    result = json.loads(out)
    assert result['review_record_added'] is False and result['attributes_preserved'] is True
    after = path.read_text()
    fm, body, _ = parse_frontmatter(after)
    assert fm == before_fm
    assert after[:-len(body)] == original[:-len(before_body)]  # YAML字节保持不变
    for heading in ['题目', '所属元技能', '相关题目', '历史记录']:
        assert extract_heading_block(before_body, heading, 3) == extract_heading_block(body, heading, 3)
    assert history_entries(before_body) == history_entries(body)
    assert facts(vault_root) == before_facts  # 反馈里的日期/状态也不能计入统计
    assert VARIANT in extract_module(body, '变式拷问')
    assert FEEDBACK in extract_module(body, '变式拷问')
    sop = extract_module(body, '提炼 SOP')
    assert sop.count('#### 错题记忆卡') == 1
    assert '#### 正确规则' not in sop  # 最终摘要收敛旧规则，不重复叠放
    assert '1. 看是否新增执行实体。' in sop
    assert extract_takeaway(body, '408') == '先辨实体再看资源'
    assert '已验收（仅指本次变式）' in body and fm['status'] == '不会'
    rc, out, _ = run_script('update_408_reflection.py', [str(path), '--feedback', FEEDBACK, *MEMORY_ARGS])
    assert rc == 0 and json.loads(out)['changed'] is False
    assert path.read_text() == after


def test_feedback_without_verified_memory_only_updates_variant(vault_root):
    path = make_card(vault_root)
    before = path.read_text()
    rc, out, err = run_script('update_408_reflection.py', [str(path), '--feedback', '结论碰巧正确，但尚未说明资源分配为何不是充分条件。'])
    assert rc == 0, out + err
    after = path.read_text()
    assert '变式状态：** 已作答' in after
    assert '错题记忆卡' not in after
    assert extract_module(before, '提炼 SOP') == extract_module(after, '提炼 SOP')
    assert '已验收' not in after


def test_incomplete_memory_and_module_overwrite_payload_are_rejected_without_writing(vault_root):
    path = make_card(vault_root)
    before = path.read_bytes()
    for args in [
        ['--feedback', '还需核对条件。', '--memory-point', '进程创建'],
        ['--feedback', '### 历史记录\n- 2026-10-20 - 会 - 不能覆盖历史'],
        ['--feedback', '使用 n=10 计算。'],
    ]:
        rc, out, _ = run_script('update_408_reflection.py', [str(path), *args])
        assert rc == 1 and json.loads(out)['error'] is True
        assert path.read_bytes() == before


def test_purpose_title_parser_ignores_lookalike_headings_in_code_and_accepts_legacy():
    body = '### 提炼 SOP\n\n```text\n### 变式拷问\n这是代码里的例子\n```\n\n先检查约束。\n\n### 变式拷问（独立作答，检验迁移）\n\n完整题面。\n'
    assert '这是代码里的例子' in extract_module(body, '提炼 SOP')
    assert extract_module(body, '变式拷问') == '完整题面。'
    assert module_span(body + '\n### 变式拷问\n重复题面。', '变式拷问') is None
