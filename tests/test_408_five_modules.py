"""五模块仅改变讲解正文，原题、学习事实、导航和统计继续走原契约。"""
from datetime import date
import json
from pathlib import Path

from helpers import run_script
from archive_ops import extract_heading_block
from card_history import history_entries
from cs_card_layout import folded_callout, unfold_callout
from dashboard_payload import collect_cards
from figure_ops import upsert_figure_section
from frontmatter import parse_frontmatter, serialize_frontmatter
from metaskill_browser import build_metaskills
from paper_card_links import associate_cards
from sync_metaskill_links import sync_links
from today_wrong_ops import extract_takeaway, scan_today_review_stats

TODAY = date(2026, 10, 20)
QID = 'qid-aaaa1234bbbb'
QUESTION = '下列操作哪些创建新进程？\nI. 登录成功\nII. 设备分配\nIII. 启动新程序任务\nA. I、II\nB. II、III\nC. I、III\nD. I、II、III'
VARIANT = '下列操作哪些创建新进程？\n\nI. 登录成功\n\nII. 设备可用，唤醒等待设备的进程\n\nIII. 启动新程序任务\n\nA. I、II\n\nB. II、III\n\nC. I、III\n\nD. I、II、III\n\n请选择并说明各陈述的依据。'


def make_card(root):
    rc, out, err = run_script('create_wrong_card.py', [
        str(root), '408', '--chapter', '进程的创建终止与信号',
        '--topic', '创建与设备分配', '--source', '2010年408真题',
        '--question-id', QID, '--question-number', '24', '--status', '不会',
        '--question-type', '选择题', '--question', QUESTION,
        '--point-location', '模块：操作系统\n章节：06.02 进程的创建终止与信号\n考点：进程创建',
        '--wrong-reason', '用户只说不会，未提供误选或推导。',
        '--diagnosis', '本题容易把已有进程的资源变化与创建新进程混淆。',
        '--breakthrough', '| 字眼 | 底层条件 |\n|---|---|\n| 创建 | 新增执行实体 |',
        '--answer-analysis', '原题答案：C。I、III成立，II只是给已有进程配置资源。',
        '--sop', '1. 看是否新增执行实体。\n2. 区分资源与状态变化。\n3. 核对前后是否同一进程。',
        '--memory-hook', '先辨实体再看资源', '--variant', VARIANT,
        '--today', TODAY.isoformat(),
    ])
    assert rc == 0, out + err
    return Path(json.loads(out)['path'])


def test_five_modules_keep_original_prompt_variant_and_review_facts_separate(vault_root):
    p = make_card(vault_root)
    fm, body, _ = parse_frontmatter(p.read_text())
    original = extract_heading_block(body, '题目', 3)
    assert '原题答案' not in original and '唤醒' not in original
    assert extract_heading_block(body, '变式拷问', 3).strip() == VARIANT
    assert body.count('> [!note]-') == 4
    assert '**本题易错机制（不等于用户已犯）**' in unfold_callout(extract_heading_block(body, '精准把脉', 3))
    assert fm['question_id'] == QID and fm['question_number'] == '24'
    assert fm['wrong_count'] == '1' and fm['next_review'] == '2026-10-21'
    assert len(history_entries(body)) == 1
    stats = scan_today_review_stats(vault_root, TODAY)
    assert stats.new_today == 1 and stats.reviewed_today == 0
    assert extract_takeaway(body, '408') == '先辨实体再看资源'
    assert len(collect_cards(vault_root, TODAY)) == 1  # 变式不是第二张卡
    questions, warnings = associate_cards(vault_root, '408', '2010年408真题', '2026-10-20')
    assert not warnings and len(questions) == 1
    assert questions[0]['question_id'] == QID and questions[0]['question_number'] == 24


def test_navigation_and_presentation_updates_preserve_attributes_history_stats_and_paper_link(vault_root):
    p = make_card(vault_root)
    fm, body, order = parse_frontmatter(p.read_text())
    fm['custom_user_field'] = '保留用户扩展属性'
    p.write_text(serialize_frontmatter(fm, order, body))
    before = p.read_text()
    before_cards = collect_cards(vault_root, TODAY)
    before_stats = scan_today_review_stats(vault_root, TODAY)
    before_paper = associate_cards(vault_root, '408', '2010年408真题', '2026-10-20')
    index = vault_root / '错题本/_元技能索引.json'
    index.write_text(json.dumps({'clusters': [
        {'id': 'm22-01', 'name': '进程创建', 'ch': '408 OS ch6 进程和线程',
         'skill': '看到什么：\n创建进程\n\n怎么做：\n1. 检查执行实体。',
         'family': '进程管理', 'qids': [QID[4:]]},
        {'id': 'm22-02', 'name': '资源管理', 'ch': '408 OS ch6 进程和线程',
         'skill': '区分资源与实体。', 'qids': [], 'also': [QID[4:]]},
    ]}, ensure_ascii=False))
    index_bytes = index.read_bytes()
    result = sync_links(vault_root, TODAY)
    assert result['updated_cards'] == 1
    after = p.read_text()
    after_fm, after_body, _ = parse_frontmatter(after)
    assert after_fm == fm
    assert '主归属' in after_body and '次归属' in after_body
    assert index.read_bytes() == index_bytes
    assert collect_cards(vault_root, TODAY) == before_cards
    assert scan_today_review_stats(vault_root, TODAY) == before_stats
    assert associate_cards(vault_root, '408', '2010年408真题', '2026-10-20') == before_paper
    for heading in ['题目', '精准把脉', '破题密码', '暴力扫雷', '提炼 SOP', '变式拷问', '历史记录']:
        assert extract_heading_block(before, heading, 3).strip() == extract_heading_block(after, heading, 3).strip()
    data = build_metaskills(vault_root, before_cards, lambda *_: None)
    assert data['total_cards'] == 1
    assert data['clusters'][0]['counts'] == {'不会': 1}
    assert data['clusters'][1]['counts'] == {}  # 次归属不重复统计
    assert sync_links(vault_root, TODAY)['written'] == 0


def test_folded_markdown_roundtrips_code_math_mermaid_quotes_and_blank_lines():
    source = '#### 机制\n\n```c\nif (i < n) {\n    a[i] = 0;\n}\n```\n\n$$\nT(n)=n+1\n$$\n\n| 量 | 值 |\n|---|---|\n| 次数 | $n$ |\n\n> 原有内层引用\n\n```mermaid\nflowchart LR\nA --> B\n```'
    wrapped = folded_callout(source, '展开解答')
    assert wrapped.startswith('> [!note]-')
    assert unfold_callout(wrapped) == source


def test_followup_figure_stays_folded_and_never_enters_variant(vault_root):
    p = make_card(vault_root)
    fm, body, _ = parse_frontmatter(p.read_text())
    first = [('错题本/_附图/one.svg', '图1：创建', 480, '')]
    second = [('错题本/_附图/two.svg', '图2：资源', 480, '')]
    updated = upsert_figure_section(body, first)
    updated = upsert_figure_section(updated, second)
    figure = extract_heading_block(updated, '图示', 3)
    assert figure.count('> [!note]-') == 1
    raw = unfold_callout(figure)
    assert raw.count('one.svg') == 1 and raw.count('two.svg') == 1
    assert updated.index('### 破题密码') < updated.index('### 图示') < updated.index('### 暴力扫雷')
    assert extract_heading_block(updated, '变式拷问', 3).strip() == VARIANT
    assert history_entries(updated) == history_entries(body)
