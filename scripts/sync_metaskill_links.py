#!/usr/bin/env python3
"""同步题卡 → 所属元技能 → 全部成员题卡的导航，不改归属或学习记录。

用法：python3 sync_metaskill_links.py [OBSIDIAN_ROOT] [--dry-run] [--today YYYY-MM-DD]
默认全量同步，兼容簇改名、题卡移动、归属调整及单题簇。
"""
import argparse
import json
import re
from pathlib import Path

from dashboard_payload import collect_cards
from env_util import atomic_write, resolve_obsidian_root
from metaskill_browser import (
    MARKDOWN_RELPATH, build_metaskills, cluster_heading, markdown_link,
    render_metaskill_markdown,
)
from study_ops import parse_today
from workbench_payload import make_link

TITLE = '### 所属元技能'
SECTION_RE = re.compile(r'^### 所属元技能[ \t]*\n.*?(?=^#{1,3} |\Z)', re.M | re.S)


def with_membership(text, links):
    block = TITLE + '\n\n' + ('\n'.join(links) if links else '尚未归簇。') + '\n\n'
    if SECTION_RE.search(text):
        return SECTION_RE.sub(lambda _: block, text, count=1)
    # 将入口放在推荐与历史之前，保留正文、原有推荐和复习记录。
    anchor = re.search(r'^### (?:相关题目|历史记录)[ \t]*$', text, re.M)
    if anchor:
        return text[:anchor.start()] + block + text[anchor.start():]
    return text.rstrip() + '\n\n' + block.rstrip() + '\n'


def sync_links(root, today, dry_run=False):
    root = Path(root).resolve()
    cards = collect_cards(root, today)
    data = build_metaskills(root, cards, make_link)
    # 缺失/损坏的索引不是空归属，不可清掉已有导航。
    if any('无法读取' in w or '尚未建立' in w for w in data['warnings']):
        return {'error': True, 'warnings': data['warnings'], 'written': 0}
    links_by_path = {}
    for cluster in data['clusters']:
        for member in cluster['members']:
            if member['missing']:
                continue
            path = Path(member['path'])
            link = markdown_link(path, root / MARKDOWN_RELPATH,
                                 cluster['name'], cluster_heading(cluster))
            links_by_path.setdefault(path, []).append(f"- {member['role']}：{link}（{cluster['id']}）")
    pending = []
    directory = root / MARKDOWN_RELPATH
    markdown = render_metaskill_markdown(data, today.isoformat())
    if not directory.exists() or directory.read_text(encoding='utf-8') != markdown:
        pending.append((directory, markdown))
    updated_cards = 0
    for card in cards:
        path = Path(card['path'])
        text = path.read_text(encoding='utf-8')
        updated = with_membership(text, links_by_path.get(path, []))
        if updated != text:
            pending.append((path, updated))
            updated_cards += 1
    if not dry_run:
        for path, content in pending:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, content)
    return {'dry_run': dry_run, 'cards': len(cards), 'clusters': len(data['clusters']),
            'updated_cards': updated_cards, 'directory_updated': any(p == directory for p, _ in pending),
            'written': 0 if dry_run else len(pending), 'unclustered': len(data['unclustered']),
            'warnings': data['warnings']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('obsidian_root', nargs='?')
    parser.add_argument('--today')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    result = sync_links(resolve_obsidian_root(args.obsidian_root), parse_today(args.today), args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('error'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
