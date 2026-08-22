"""test update_card.py"""
import json
import textwrap
from datetime import date
from pathlib import Path

from helpers import run_script

TODAY = "2026-03-23"


def test_status_buhui(sample_card):
    """不会：interval→1, ease×0.8"""
    rc, out, _ = run_script("update_card.py", [
        str(sample_card), "--status", "不会", "--comment", "完全忘了", "--today", TODAY
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["interval"] == 1
    assert float(data["ease_factor"]) == 2.0  # 2.5 * 0.8
    assert data["next_review"] == "2026-03-24"


def test_status_banhui(sample_card):
    """半会：interval×1.2(至少+1), ease不变"""
    rc, out, _ = run_script("update_card.py", [
        str(sample_card), "--status", "半会", "--comment", "有进步", "--today", TODAY
    ])
    assert rc == 0
    data = json.loads(out)
    # old_interval=4, 4*1.2=4.8→int=4, max(4, 4+1)=5
    assert data["interval"] == 5
    assert data["ease_factor"] == "2.50"


def test_status_hui(sample_card):
    """会：interval×ease_factor(上限90), ease+0.1"""
    rc, out, _ = run_script("update_card.py", [
        str(sample_card), "--status", "会", "--comment", "掌握了", "--today", TODAY
    ])
    assert rc == 0
    data = json.loads(out)
    # old_interval=4, 4*2.5=10
    assert data["interval"] == 10
    assert float(data["ease_factor"]) == 2.6


def test_ease_floor(sample_card):
    """反复不会，ease 不低于 1.3"""
    for _ in range(5):
        run_script("update_card.py", [str(sample_card), "--status", "不会", "--today", TODAY])
    rc, out, _ = run_script("update_card.py", [str(sample_card), "--status", "不会", "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert float(data["ease_factor"]) >= 1.3


def test_interval_cap(sample_card):
    """会的 interval 上限为 90 天"""
    # 先手动把 interval 设高
    text = sample_card.read_text()
    text = text.replace("review_interval: 4", "review_interval: 80")
    sample_card.write_text(text)

    rc, out, _ = run_script("update_card.py", [str(sample_card), "--status", "会", "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert data["interval"] <= 90


def test_zero_interval_is_treated_as_new_card_baseline(sample_card):
    text = sample_card.read_text(encoding="utf-8").replace("review_interval: 4", "review_interval: 0")
    sample_card.write_text(text, encoding="utf-8")

    rc, out, _ = run_script("update_card.py", [str(sample_card), "--status", "会", "--today", TODAY])

    assert rc == 0
    data = json.loads(out)
    assert data["interval"] == 2


def test_missing_interval_uses_new_card_baseline(sample_card_no_qid):
    text = sample_card_no_qid.read_text(encoding="utf-8").replace("review_interval: 1\n", "")
    sample_card_no_qid.write_text(text, encoding="utf-8")

    rc, out, _ = run_script("update_card.py", [str(sample_card_no_qid), "--status", "半会", "--today", TODAY])

    assert rc == 0
    data = json.loads(out)
    assert data["interval"] == 2


def test_qid_backfill(sample_card_no_qid):
    """回填 question_id 并重命名文件"""
    rc, out, _ = run_script("update_card.py", [
        str(sample_card_no_qid), "--status", "半会",
        "--question-id", "qid-aabbccddeeff", "--today", TODAY
    ])
    assert rc == 0
    data = json.loads(out)
    assert "renamed_from" in data
    assert "qid-aabbccddeeff" in data["updated"]
    # 原文件应该不存在了
    assert not sample_card_no_qid.exists()


def test_qid_conflict(sample_card):
    """传入不同的 question_id 应报错"""
    rc, out, _ = run_script("update_card.py", [
        str(sample_card), "--status", "会",
        "--question-id", "qid-999999999999", "--today", TODAY
    ])
    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True


def test_rename_conflict_does_not_mutate_original(sample_card_no_qid, vault_root):
    """目标规范文件已存在时，原卡不应被半提交改写。"""
    existing = sample_card_no_qid.with_name("泰勒展开-660题-qid-aabbccddeeff.md")
    existing.write_text("---\nquestion_id: qid-aabbccddeeff\n---\n", encoding="utf-8")
    before = sample_card_no_qid.read_text(encoding="utf-8")

    rc, out, _ = run_script("update_card.py", [
        str(sample_card_no_qid), "--status", "半会",
        "--question-id", "qid-aabbccddeeff", "--today", TODAY
    ])

    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True
    assert "目标文件已存在" in data["message"]
    assert sample_card_no_qid.read_text(encoding="utf-8") == before


def test_history_append(sample_card):
    """历史记录应追加新行"""
    run_script("update_card.py", [str(sample_card), "--status", "会", "--comment", "搞定", "--today", TODAY])
    text = sample_card.read_text()
    assert f"- {TODAY} - 会 - 搞定" in text


def test_file_not_found():
    rc, out, _ = run_script("update_card.py", [
        "/nonexistent/card.md", "--status", "不会", "--today", TODAY
    ])
    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True


def test_rejects_non_wrongbook_path(tmp_path):
    stray = tmp_path / "note.md"
    stray.write_text("---\nstatus: 半会\n---\n", encoding="utf-8")

    rc, out, _ = run_script("update_card.py", [
        str(stray), "--status", "会", "--today", TODAY
    ])

    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True
    assert "错题本目录下" in data["message"]


def test_invalid_question_id_is_rejected(sample_card_no_qid):
    rc, out, _ = run_script("update_card.py", [
        str(sample_card_no_qid), "--status", "半会",
        "--question-id", "qid-../../escape", "--today", TODAY
    ])

    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True


def test_rename_preserves_single_updated_file(sample_card_no_qid):
    rc, out, _ = run_script("update_card.py", [
        str(sample_card_no_qid), "--status", "半会",
        "--question-id", "qid-aabbccddeeff", "--comment", "回填后继续复习", "--today", TODAY
    ])

    assert rc == 0
    data = json.loads(out)
    new_path = sample_card_no_qid.with_name(data["updated"])
    assert not sample_card_no_qid.exists()
    assert new_path.exists()
    content = new_path.read_text(encoding="utf-8")
    assert "question_id: qid-aabbccddeeff" in content
    assert f"- {TODAY} - 半会 - 回填后继续复习" in content


def test_update_card_preserves_legacy_option_section(vault_root):
    """老卡（ccce449 前建的）仍可能保留 `### 选项（如有）` 区块，update_card.py 不应清掉它。"""
    card_dir = vault_root / "错题本" / "408" / "数据结构"
    card_dir.mkdir(parents=True, exist_ok=True)
    legacy_card = card_dir / "二叉树遍历-王道-qid-1234567890ab.md"
    legacy_card.write_text(textwrap.dedent("""\
        ---
        source: 王道
        question_id: qid-1234567890ab
        topic: 二叉树遍历
        error_tags: []
        first_wrong_at: 2026-04-01
        last_review_at: 2026-04-01
        wrong_count: 1
        status: 不会
        next_review: 2026-04-02
        review_interval: 1
        ease_factor: 2.50
        ---

        #subject/408 #topic/树 #status/不会 #source/王道

        ## 二叉树遍历 — 王道 — qid-1234567890ab

        ### 题目
        - 下列关于二叉树遍历的说法，正确的是：

        ### 选项（如有）
        - A. 先序遍历一定有序
        - B. 中序遍历可还原任意二叉树
        - C. 后序遍历需要栈
        - D. 层序遍历不需要队列

        ### 历史记录
        - 2026-04-01 - 不会 - 首次
    """), encoding="utf-8")

    rc, _, _ = run_script("update_card.py", [
        str(legacy_card), "--status", "半会", "--comment", "再做一遍", "--today", TODAY
    ])

    assert rc == 0
    content = legacy_card.read_text(encoding="utf-8")
    # 老的选项区块必须原样保留
    assert "### 选项（如有）" in content
    assert "A. 先序遍历一定有序" in content
    assert "D. 层序遍历不需要队列" in content
    # 同时正常完成 update_card 的本职：status + 历史记录
    assert "status: 半会" in content
    assert f"- {TODAY} - 半会 - 再做一遍" in content


# ---------- 复习时补图 ----------

FIGURE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 320">
  <style>:root{--ink:#1f2933;--bg:#fdfdfb}
  @media (prefers-color-scheme: dark){:root{--ink:#e6e8eb;--bg:#1e1f22}}
  text{font-family:Arial,sans-serif;font-size:14px}
  .bg{fill:var(--bg)} .ink{fill:var(--ink)}</style>
  <rect class="bg" width="480" height="320" fill="#fdfdfb"/>
  <text class="ink" x="40" y="40" fill="#1f2933">D</text>
</svg>"""


def make_figure(vault_root, question_id, slug, caption):
    import os
    import subprocess
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    result = subprocess.run(
        ["python3", str(scripts_dir / "create_figure.py"), str(vault_root),
         "--question-id", question_id, "--slug", slug, "--caption", caption],
        input=FIGURE_SVG, capture_output=True, text=True,
        env=os.environ.copy(), cwd=str(scripts_dir),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)["figure_arg"]


def test_figure_section_inserted_above_anchor_section(vault_root, sample_card):
    figure_arg = make_figure(vault_root, "qid-f728c5b18974", "极坐标区域", "图1：极坐标下的积分区域")
    rc, out, err = run_script("update_card.py", [
        str(sample_card), "--status", "半会", "--comment", "补了张图", "--figure", figure_arg,
    ])
    assert rc == 0, out + err
    assert json.loads(out)["figure_added"] == 1
    text = sample_card.read_text(encoding="utf-8")
    assert "### 图示" in text
    assert text.index("### 正确思路 / 核心结论") < text.index("### 图示") < text.index("### 易错点 / 变式提醒")
    assert "- 图1：极坐标下的积分区域" in text


def test_second_figure_appends_instead_of_overwriting(vault_root, sample_card):
    first = make_figure(vault_root, "qid-f728c5b18974", "极坐标区域", "图1：极坐标下的积分区域")
    run_script("update_card.py", [str(sample_card), "--status", "半会", "--figure", first])
    second = make_figure(vault_root, "qid-f728c5b18974", "换序后", "图2：换序后的条带方向")
    rc, out, err = run_script("update_card.py", [str(sample_card), "--status", "会", "--figure", second])
    assert rc == 0, out + err
    text = sample_card.read_text(encoding="utf-8")
    assert text.count("### 图示") == 1
    assert "图1：极坐标下的积分区域" in text
    assert "图2：换序后的条带方向" in text
    # 图示区块与下一个小节之间必须留空行，否则 Obsidian 里会挤成一坨
    assert "\n\n### 易错点 / 变式提醒" in text


def test_update_without_figure_leaves_card_untouched(vault_root, sample_card):
    rc, out, err = run_script("update_card.py", [str(sample_card), "--status", "会"])
    assert rc == 0, out + err
    assert "figure_added" not in json.loads(out)
    assert "### 图示" not in sample_card.read_text(encoding="utf-8")


def test_rejects_figure_pointing_outside_vault(vault_root, sample_card, tmp_path):
    outside = tmp_path.parent / "outside-update.svg"
    outside.write_text(FIGURE_SVG, encoding="utf-8")
    rc, out, _ = run_script("update_card.py", [
        str(sample_card), "--status", "会", "--figure", f"{outside}|图1：越界",
    ])
    assert rc == 1
    assert "vault 之外" in json.loads(out)["message"]
