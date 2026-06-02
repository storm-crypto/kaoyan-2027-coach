"""test migrate_wrong_card_layout.py"""
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from helpers import run_script


CARD_DIR_PARTS = ("错题本", "数学一", "高等数学")


def _write_card(vault_root, name, body):
    card_dir = vault_root.joinpath(*CARD_DIR_PARTS)
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / name
    card.write_text(body, encoding="utf-8")
    return card


CRAMMED_POINT_JUDGMENT_CARD = """---
source: 李林
question_id: qid-26dbfe4441c1
topic: 反三角复合积分
status: 不会
---

#subject/math1 #topic/反三角复合积分 #status/不会 #source/李林

## 反三角复合积分 — 李林 — qid-26dbfe4441c1

### 题目
- (IV) $$\\int \\frac{\\arctan x}{x^2(1+x^2)}\\,dx$$。

### 考点判断
- 题型：反三角函数与有理式复合的不定积分。章节：不定积分的计算。考点：反三角整体换元、三角恒等变形、分部积分。难度：中等。考频：常见模型。突破口：令 $t=\\arctan x$，把代数结构转成三角结构。

### 第一步怎么想到
- 先看结构。

### 历史记录
- 2026-06-02 - 不会 - 首次
"""


def test_dry_run_reports_without_writing(vault_root):
    card = _write_card(vault_root, "反三角-李林-qid-26dbfe4441c1.md", CRAMMED_POINT_JUDGMENT_CARD)
    before = card.read_text(encoding="utf-8")

    rc, out, _ = run_script("migrate_wrong_card_layout.py", [str(vault_root)])

    assert rc == 0
    data = json.loads(out)
    assert data["applied"] is False
    assert data["summary"]["changed_count"] == 1
    assert data["changed"][0]["label_splits"] == ["考点判断"]
    # dry-run 不写盘
    assert card.read_text(encoding="utf-8") == before


def test_apply_splits_crammed_point_judgment_and_preserves_latex(vault_root):
    card = _write_card(vault_root, "反三角-李林-qid-26dbfe4441c1.md", CRAMMED_POINT_JUDGMENT_CARD)

    rc, out, _ = run_script("migrate_wrong_card_layout.py", [str(vault_root), "--apply"])

    assert rc == 0
    data = json.loads(out)
    assert data["applied"] is True
    assert data["summary"]["changed_count"] == 1
    content = card.read_text(encoding="utf-8")
    assert "- 题型：反三角函数与有理式复合的不定积分" in content
    assert "- 章节：不定积分的计算" in content
    assert "- 难度：中等" in content
    # 突破口里的 LaTeX 和内部句号整段保留，只去掉末尾分隔句号
    assert "- 突破口：令 $t=\\arctan x$，把代数结构转成三角结构" in content
    # 原来挤成一行的形态消失
    assert "。章节：" not in content
    assert "。突破口：" not in content


def test_apply_never_touches_frontmatter_question_history(vault_root):
    card = _write_card(vault_root, "反三角-李林-qid-26dbfe4441c1.md", CRAMMED_POINT_JUDGMENT_CARD)

    rc, _, _ = run_script("migrate_wrong_card_layout.py", [str(vault_root), "--apply"])

    assert rc == 0
    content = card.read_text(encoding="utf-8")
    assert "question_id: qid-26dbfe4441c1" in content
    assert "### 题目\n- (IV) $$\\int \\frac{\\arctan x}{x^2(1+x^2)}\\,dx$$。" in content
    assert "### 历史记录\n- 2026-06-02 - 不会 - 首次" in content


def test_idempotent_second_run_no_change(vault_root):
    _write_card(vault_root, "反三角-李林-qid-26dbfe4441c1.md", CRAMMED_POINT_JUDGMENT_CARD)

    rc1, _, _ = run_script("migrate_wrong_card_layout.py", [str(vault_root), "--apply"])
    rc2, out2, _ = run_script("migrate_wrong_card_layout.py", [str(vault_root), "--apply"])

    assert rc1 == 0 and rc2 == 0
    data2 = json.loads(out2)
    assert data2["summary"]["changed_count"] == 0


BROKEN_BLOCK_MATH_CARD = """---
source: 李林
question_id: qid-aabbccdd1122
topic: 块公式破损
status: 不会
---

#subject/math1 #topic/块公式破损 #status/不会 #source/李林

## 块公式破损 — 李林 — qid-aabbccdd1122

### 题目
- 求不定积分。

### 考点判断
- 题型：换元降维

### 规范解法
- 先令 $t=\\arctan x$。
- $$
- I=\\int t\\cot^2t\\,dt.
- $$
- 再用恒等式收口。

### 历史记录
- 2026-06-02 - 不会 - 首次
"""


def test_unwraps_bulleted_block_math(vault_root):
    card = _write_card(vault_root, "块公式-李林-qid-aabbccdd1122.md", BROKEN_BLOCK_MATH_CARD)

    rc, out, _ = run_script("migrate_wrong_card_layout.py", [str(vault_root), "--apply"])

    assert rc == 0
    data = json.loads(out)
    assert data["changed"][0]["formula_unwraps"] == ["规范解法"]
    content = card.read_text(encoding="utf-8")
    assert "- $$" not in content
    assert "$$\nI=\\int t\\cot^2t\\,dt.\n$$" in content
    # 块外的解释行仍保留 bullet
    assert "- 先令 $t=\\arctan x$。" in content
    assert "- 再用恒等式收口。" in content


OVERLONG_PROSE_CARD = """---
source: 李林
question_id: qid-99887766aabb
topic: 超长散文
status: 不会
---

#subject/math1 #topic/超长散文 #status/不会 #source/李林

## 超长散文 — 李林 — qid-99887766aabb

### 题目
- 求极限。

### 考点判断
- 题型：极限

### 第一步怎么想到
- 先观察题目里给定的结构再联想可以调用的定理并逐条核对条件是否满足然后代入验证最后才能决定走哪条路这一整段话被压成了一个超长的项目符号根本没有拆分非常难以复习而且把好几步推理和判断全都堆在同一行里读起来完全分不清层次也找不到重点应该拆成多条每条只写一个动作

### 历史记录
- 2026-06-02 - 不会 - 首次
"""


def test_overlong_prose_flagged_not_split(vault_root):
    card = _write_card(vault_root, "超长-李林-qid-99887766aabb.md", OVERLONG_PROSE_CARD)
    before = card.read_text(encoding="utf-8")

    rc, out, _ = run_script("migrate_wrong_card_layout.py", [str(vault_root)])

    assert rc == 0
    data = json.loads(out)
    # 超长散文只报告，不自动拆 → 文件不变
    assert data["summary"]["changed_count"] == 0
    assert card.read_text(encoding="utf-8") == before
    review = data["overlong_manual_review"]
    assert len(review) == 1
    assert review[0]["flags"][0]["section"] == "第一步怎么想到"


INLINE_WALL_CARD = """---
source: 李林
question_id: qid-aa11bb22cc33
topic: 行内公式墙
status: 不会
---

#subject/math1 #topic/行内公式墙 #status/不会 #source/李林

## 行内公式墙 — 李林 — qid-aa11bb22cc33

### 题目
- 求该积分。

### 规范解法
取 $u=\\arctan\\sqrt{e^x-1}$，$dv=e^{2x}dx$，则 $v=\\frac{1}{2}e^{2x}$。设 $y=\\sqrt{e^x-1}$，则 $y'=\\frac{e^x}{2\\sqrt{e^x-1}}$，且 $1+y^2=e^x$，所以 $u'=\\frac{1}{2\\sqrt{e^x-1}}$。

### 历史记录
- 2026-06-02 - 不会 - 首次
"""


def test_inline_math_wall_flagged_not_changed(vault_root):
    """规范解法挤成一行连排多段行内 $...$ → 单列 inline_wall_manual_review，文件不动。"""
    card = _write_card(vault_root, "行内墙-李林-qid-aa11bb22cc33.md", INLINE_WALL_CARD)
    before = card.read_text(encoding="utf-8")

    rc, out, _ = run_script("migrate_wrong_card_layout.py", [str(vault_root)])

    assert rc == 0
    data = json.loads(out)
    # 无法安全自动拆 → 只报告，不改写
    assert data["summary"]["changed_count"] == 0
    assert card.read_text(encoding="utf-8") == before
    review = data["inline_wall_manual_review"]
    assert len(review) == 1
    assert review[0]["flags"][0]["section"] == "规范解法"
    assert data["summary"]["inline_wall_count"] == 1


def test_multistep_formal_solution_not_flagged_as_inline_wall(vault_root):
    """分步、短设定行、块公式独立成行的规范解法不应被误报为行内公式墙。"""
    card = _write_card(vault_root, "块公式-李林-qid-aabbccdd1122.md", BROKEN_BLOCK_MATH_CARD)

    rc, out, _ = run_script("migrate_wrong_card_layout.py", [str(vault_root), "--apply"])

    assert rc == 0
    data = json.loads(out)
    assert data["summary"]["inline_wall_count"] == 0
    assert data["inline_wall_manual_review"] == []
