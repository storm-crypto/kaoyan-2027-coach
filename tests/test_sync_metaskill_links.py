"""题卡 ⇄ 元技能目录的真实目标、全量成员与源记录保留。"""
from datetime import date
import json
import re
from urllib.parse import unquote

from sync_metaskill_links import sync_links, SECTION_RE
from test_metaskill_browser import cluster, put_index

TODAY = date(2026, 10, 18)
QID = 'f728c5b18974'


def targets(path):
    for href in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        target, _, fragment = href.partition('#')
        yield (path.parent / unquote(target)).resolve(), unquote(fragment)


def test_roundtrip_all_members_and_primary_secondary_links(vault_root, sample_card):
    cards = [sample_card]
    qids = [QID]
    for i in range(5):
        qid = f'{i:012x}'
        path = sample_card.with_name(f'同类题 ({i})-qid-{qid}.md')
        path.write_text(sample_card.read_text().replace(QID, qid))
        cards.append(path)
        qids.append(qid)
    index = put_index(vault_root, [cluster('m01-01', qids), cluster('m01-02', [], [QID])])
    original = {p: p.read_bytes() for p in [index, *cards]}
    result = sync_links(vault_root, TODAY)
    assert result['updated_cards'] == 6
    directory = vault_root / '错题本/元技能目录.md'
    assert '主归属' in sample_card.read_text() and '次归属' in sample_card.read_text()
    # 逐个验证：题卡入口确实指向生成的标题；目录成员完整且能回到真实文件。
    for path in cards:
        for target, heading in targets(path):
            assert target == directory
            assert f'### {heading}\n' in target.read_text()
        assert SECTION_RE.sub('', path.read_text()) == original[path].decode()
    member_targets = {target for target, heading in targets(directory) if not heading}
    assert member_targets == set(cards)
    assert index.read_bytes() == original[index]
    snapshot = {p: p.read_bytes() for p in [index, directory, *cards]}
    assert sync_links(vault_root, TODAY)['written'] == 0
    assert snapshot == {p: p.read_bytes() for p in snapshot}


def test_singleton_rename_move_and_membership_removal(vault_root, sample_card):
    index = put_index(vault_root, [cluster('m01-01', [QID])])
    sync_links(vault_root, TODAY)
    assert '主归属' in sample_card.read_text()
    moved = sample_card.parent / '更深的目录' / sample_card.name
    moved.parent.mkdir()
    sample_card.rename(moved)
    data = json.loads(index.read_text())
    data['clusters'][0]['name'] = '新名称 [含括号] | 动作'
    index.write_text(json.dumps(data, ensure_ascii=False))
    sync_links(vault_root, TODAY)
    for target, heading in targets(moved):
        assert f'### {heading}\n' in target.read_text()
        assert '新名称' in heading
    directory = vault_root / '错题本/元技能目录.md'
    assert moved in {target for target, heading in targets(directory) if not heading}
    put_index(vault_root, [])
    sync_links(vault_root, TODAY)
    assert '尚未归簇' in moved.read_text()
    assert not list(targets(moved))


def test_dry_run_and_unreadable_index_preserve_navigation(vault_root, sample_card):
    index = put_index(vault_root, [cluster('m01-01', [QID])])
    before = sample_card.read_bytes()
    result = sync_links(vault_root, TODAY, dry_run=True)
    assert result['updated_cards'] == 1 and result['written'] == 0
    assert sample_card.read_bytes() == before
    assert not (vault_root / '错题本/元技能目录.md').exists()
    sync_links(vault_root, TODAY)
    directory = vault_root / '错题本/元技能目录.md'
    snapshot = (directory.read_bytes(), sample_card.read_bytes())
    index.write_text('{broken')
    assert sync_links(vault_root, TODAY)['error']
    assert snapshot == (directory.read_bytes(), sample_card.read_bytes())
    index.unlink()
    assert sync_links(vault_root, TODAY)['error']
    assert snapshot == (directory.read_bytes(), sample_card.read_bytes())
