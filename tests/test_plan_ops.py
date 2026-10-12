"""归档、任务区完成率和 AI 正文写入契约。"""
from datetime import date, timedelta

import pytest

from archive_ops import archive_daily_plan
from plan_ops import write_daily_plan, yesterday_completion_rate

TODAY = date(2026, 10, 12)


def test_archive_uses_title_date_and_is_idempotent(vault_root):
    current = vault_root / '周计划/_今日计划.md'
    current.write_text('# 今日计划：2026-10-11\n\n## 任务清单\n- [x] 已完成\n')
    saved = archive_daily_plan(vault_root, TODAY)
    assert saved.name == '_今日计划-2026-10-11.md'
    original = saved.read_bytes()
    assert archive_daily_plan(vault_root, TODAY) == saved
    assert saved.read_bytes() == original
    assert len(list(current.parent.glob('_今日计划-*.md'))) == 1


@pytest.mark.parametrize('title', ['没有日期', '# 今日计划：2026-02-30'])
def test_archive_falls_back_to_today(vault_root, title):
    (vault_root / '周计划/_今日计划.md').write_text(title)
    assert archive_daily_plan(vault_root, TODAY).name == '_今日计划-2026-10-12.md'


def test_archive_cleans_expired_even_without_current_plan(vault_root):
    folder = vault_root / '周计划'
    expired = folder / f'_今日计划-{(TODAY - timedelta(days=31)).isoformat()}.md'
    retained = folder / f'_今日计划-{(TODAY - timedelta(days=30)).isoformat()}.md'
    malformed = folder / '_今日计划-2026-99-99.md'
    unrelated = folder / '_候选池-2026-01-01.json'
    for path in (expired, retained, malformed, unrelated):
        path.write_text('keep')
    assert archive_daily_plan(vault_root, TODAY) is None
    assert not expired.exists()
    assert retained.exists() and malformed.exists() and unrelated.exists()


def test_completion_only_counts_task_section(vault_root):
    yesterday = vault_root / '周计划/_今日计划-2026-10-11.md'
    yesterday.write_text('''# 今日计划：2026-10-11
## 排计划依据
- [ ] 正文中的 checkbox
## 任务清单
- [x] [数学一] 定积分（1 小时）
- [X] [408] 调度
### 下午
- [ ] [英语一] 阅读
```markdown
- [ ] 代码示例
```
## 收尾提醒
- [ ] 不计入任务
''')
    assert yesterday_completion_rate(vault_root, TODAY) == (2 / 3, ['[英语一] 阅读'])


def test_completion_missing_or_empty_archive(vault_root):
    assert yesterday_completion_rate(vault_root, TODAY) == (None, [])
    path = vault_root / '周计划/_今日计划-2026-10-11.md'
    path.write_text('## 任务清单\n没有任务\n')
    assert yesterday_completion_rate(vault_root, TODAY) == (0.0, [])
    path.write_text('## 排计划依据\n- [x] 不是任务\n')
    assert yesterday_completion_rate(vault_root, TODAY) == (0.0, [])


def test_write_archives_before_overwrite_and_preserves_same_day_completed(vault_root):
    target = vault_root / '周计划/_今日计划.md'
    previous = '# 今日计划：2026-10-11\n## 任务清单\n- [x] [数学一] 旧任务（1 小时）\n'
    target.write_text(previous)
    new = '# 今日计划：2026-10-12\n## 任务清单\n- [ ] [数学一] 新任务（1 小时）\n'
    assert write_daily_plan(vault_root, TODAY, new) == target
    assert (target.parent / '_今日计划-2026-10-11.md').read_text() == previous
    target.write_text(new.replace('[ ]', '[x]') + '  - 独立完成\n')
    write_daily_plan(vault_root, TODAY, new)
    assert '- [x]' in target.read_text() and '独立完成' in target.read_text()


def test_invalid_write_does_not_touch_previous_plan(vault_root):
    target = vault_root / '周计划/_今日计划.md'
    target.write_text('原始文件')
    with pytest.raises(ValueError):
        write_daily_plan(vault_root, TODAY, '# 今日计划：2026-10-10')
    assert target.read_text() == '原始文件'


def test_rollover_refreshes_snapshot_after_same_day_replan(vault_root):
    current = '# 今日计划：2026-10-12\n## 任务清单\n- [ ] [数学一] 换元（1 小时）\n'
    write_daily_plan(vault_root, TODAY, current)
    write_daily_plan(vault_root, TODAY, current)
    target = vault_root / '周计划/_今日计划.md'
    target.write_text(current.replace('[ ]', '[x]'))
    tomorrow = TODAY + timedelta(days=1)
    archive_daily_plan(vault_root, tomorrow)
    assert yesterday_completion_rate(vault_root, tomorrow) == (1.0, [])
    assert len(list(target.parent.glob('_今日计划-*.md'))) == 1
