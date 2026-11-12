"""test scan_due_reviews.py"""
import json
from datetime import date, timedelta
import pytest
from helpers import run_script
from frontmatter import parse_frontmatter
from study_ops import collect_due_cards

TODAY = "2026-06-15"
TODAY_DATE = date.fromisoformat(TODAY)


def _make_card(vault_root, name, next_review, interval, status="半会", question_lines=None, option_lines=None):
    card_dir = vault_root / "错题本" / "数学一" / "高等数学"
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / name
    question_block = "### 题目\n- 设二重积分区域 D 为单位圆与第一象限的交集，求积分值。\n"
    if question_lines is not None:
        question_block = "### 题目\n" + "\n".join(question_lines) + "\n"

    option_block = ""
    if option_lines is not None:
        option_block = "### 选项（如有）\n" + "\n".join(option_lines) + "\n"

    content = (
        "---\n"
        "source: test\n"
        "question_id: qid-000000000001\n"
        "topic: test topic\n"
        "first_wrong_at: 2026-01-01\n"
        "last_review_at: 2026-01-01\n"
        "wrong_count: 1\n"
        f"status: {status}\n"
        f"next_review: {next_review}\n"
        f"review_interval: {interval}\n"
        "ease_factor: 2.50\n"
        "---\n\n"
        "## Test card\n\n"
        f"{question_block}\n"
        f"{option_block}"
        "### 错误原因\n"
        "- 计算时把上下限写反了\n"
    )
    card.write_text(content, encoding="utf-8")
    return card


def test_due_today(vault_root):
    _make_card(vault_root, "due-today.md", TODAY, 2)
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert len(data["due"]) == 1
    assert data["due"][0]["filename"] == "due-today"
    assert "单位圆与第一象限" in data["due"][0]["question_text"]
    assert "单位圆与第一象限" in data["due"][0]["question_preview"]


def test_due_card_includes_options(vault_root):
    _make_card(
        vault_root,
        "with-options.md",
        TODAY,
        2,
        question_lines=["- 下列关于进程调度的说法，正确的是："],
        option_lines=[
            "- A. FCFS 一定优于短作业优先",
            "- B. 带权周转时间越小越好",
            "- C. 时间片轮转不会发生上下文切换",
            "- D. 周转时间与服务时间总是相等",
        ],
    )
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    item = next(card for card in data["due"] if card["filename"] == "with-options")
    assert "进程调度" in item["question_text"]
    assert "A. FCFS" in item["question_text"]
    assert "B. 带权周转时间越小越好" in item["question_text"]
    assert "A. FCFS" in item["options_text"]
    assert "B. 带权周转时间越小越好" in item["options_text"]


def test_due_card_with_new_structure_reads_options_from_question_block(vault_root):
    _make_card(
        vault_root,
        "new-structure.md",
        TODAY,
        2,
        question_lines=[
            "- 下列关于进程调度的说法，正确的是：",
            "- A. FCFS 一定优于短作业优先",
            "- B. 带权周转时间越小越好",
            "- C. 时间片轮转不会发生上下文切换",
            "- D. 周转时间与服务时间总是相等",
        ],
        option_lines=None,
    )
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    item = next(card for card in data["due"] if card["filename"] == "new-structure")
    assert "A. FCFS" in item["question_text"]
    assert "B. 带权周转时间越小越好" in item["question_text"]
    assert item["options_text"] == ""


def test_not_yet_due(vault_root):
    tomorrow = (TODAY_DATE + timedelta(days=1)).isoformat()
    _make_card(vault_root, "future.md", tomorrow, 2)
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert len(data["due"]) == 0


def test_default_scan_reports_overdue_without_writing(vault_root):
    overdue = (TODAY_DATE - timedelta(days=10)).isoformat()
    card = _make_card(vault_root, "overdue.md", overdue, 8)
    before = card.read_bytes()
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert data["degraded"] == 0
    assert data["pending_overdue"] == 1
    assert "--apply-overdue" in data["overdue_warning"]
    assert len(data["due"]) == 1
    assert data["due"][0]["review_interval"] == 8
    assert data["due"][0]["overdue_days"] == 10
    assert data["due"][0]["overdue_reset_pending"] is True
    assert card.read_bytes() == before


def test_explicit_overdue_reset_changes_only_schedule_and_is_idempotent(vault_root):
    overdue = (TODAY_DATE - timedelta(days=10)).isoformat()
    card = _make_card(vault_root, "overdue.md", overdue, 90, status="会")
    text = card.read_text() + "\n### 历史记录\n- 2026-01-01 - 会 - 独立完成\n"
    card.write_text(text, encoding="utf-8")
    before_fm, before_body, _ = parse_frontmatter(text)
    args = [str(vault_root), "--today", TODAY, "--apply-overdue"]
    rc, out, err = run_script("scan_due_reviews.py", args)
    assert rc == 0, err
    data = json.loads(out)
    assert data["degraded"] == 1
    assert data["pending_overdue"] == 0
    assert len(data["due"]) == 1
    assert data["due"][0]["review_interval"] == 1
    after_fm, after_body, _ = parse_frontmatter(card.read_text())
    assert after_fm == {**before_fm, "review_interval": "1", "next_review": TODAY}
    assert after_body == before_body
    after = card.read_bytes()
    rc, out, err = run_script("scan_due_reviews.py", args)
    assert rc == 0, err
    assert json.loads(out)["degraded"] == 0
    assert json.loads(out)["pending_overdue"] == 0
    assert card.read_bytes() == after


@pytest.mark.parametrize("interval", [90, 96])
def test_long_interval_cards_still_due(vault_root, interval):
    """90 天是间隔上限，旧卡超过上限也不能从到期队列消失。"""
    _make_card(vault_root, "long-interval.md", TODAY, interval, status="会")
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert len(data["due"]) == 1
    assert data["due"][0]["review_interval"] == interval


def test_scan_dashboard_and_context_share_due_set_without_mutating(vault_root):
    from dashboard_payload import collect_cards

    _make_card(vault_root, "today-90.md", TODAY, 90, status="会")
    _make_card(vault_root, "overdue-96.md", "2026-06-01", 96, status="半会")
    _make_card(vault_root, "future.md", "2026-06-16", 2)
    _make_card(vault_root, "unscheduled.md", "invalid", 2)
    before = {p: p.read_bytes() for p in vault_root.rglob("*.md")}
    rc, out, err = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0, err
    scanner_paths = {item["path"] for item in json.loads(out)["due"]}
    context_paths = {item["path"] for item in collect_due_cards(vault_root, TODAY_DATE)}
    dashboard_paths = {item["path"] for item in collect_cards(vault_root, TODAY_DATE) if item["is_due"]}
    assert len(scanner_paths) == 2
    assert scanner_paths == context_paths == dashboard_paths
    assert {p: p.read_bytes() for p in vault_root.rglob("*.md")} == before


@pytest.mark.parametrize("index_text", [None, '{"clusters": []}', '{broken'])
def test_unavailable_index_preserves_due_cards_in_unclustered_bucket(vault_root, index_text):
    card = _make_card(vault_root, "unclustered.md", TODAY, 2)
    if index_text is not None:
        (vault_root / "错题本/_元技能索引.json").write_text(index_text, encoding="utf-8")
    before = {p: p.read_bytes() for p in vault_root.rglob("*") if p.is_file()}
    rc, out, err = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY, "--by-cluster"])
    assert rc == 0, err
    data = json.loads(out)
    assert data["cluster_warning"]
    assert len(data["clusters"]) == 1
    assert data["clusters"][0]["cluster_id"] == "unclustered"
    assert data["clusters"][0]["due_count"] == 1
    assert data["clusters"][0]["cards"][0]["path"] == str(card)
    assert {p: p.read_bytes() for p in vault_root.rglob("*") if p.is_file()} == before


def test_empty_dir(vault_root):
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert data["due"] == []
    assert data["degraded"] == 0


def test_env_var(vault_root):
    _make_card(vault_root, "env-test.md", TODAY, 2)
    rc, out, _ = run_script("scan_due_reviews.py", ["--today", TODAY],
                            env_extra={"KAOYAN_OBSIDIAN_ROOT": str(vault_root)})
    assert rc == 0
    data = json.loads(out)
    assert len(data["due"]) == 1


def test_plain_converts_latex(vault_root):
    """--plain 标志将 LaTeX 公式转为 Unicode 可读文本。"""
    _make_card(
        vault_root,
        "latex-card.md",
        TODAY,
        2,
        question_lines=["- 若 $f''(x) > 0$，求 $\\frac{1}{2}$ 的值。"],
        option_lines=[
            "- A. $x^2 + 1$",
            "- B. $\\sqrt{x}$",
        ],
    )
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY, "--plain"])
    assert rc == 0
    data = json.loads(out)
    item = data["due"][0]
    # LaTeX $ 定界符应被去除
    assert "$" not in item["question_text"]
    assert "$" not in item["options_text"]
    assert "$" not in item["question_preview"]
    # Unicode 转写后应包含可读内容
    assert "1/2" in item["question_text"]       # \frac{1}{2} → 1/2
    assert "x² + 1" in item["question_text"]
    assert "\u221a" in item["options_text"]      # \sqrt → √


def test_plain_flag_absent_keeps_latex(vault_root):
    """不带 --plain 时，LaTeX 原样保留。"""
    _make_card(
        vault_root,
        "raw-card.md",
        TODAY,
        2,
        question_lines=["- 求 $\\frac{a}{b}$ 的值。"],
    )
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert "$" in data["due"][0]["question_text"]
    assert "\\frac" in data["due"][0]["question_text"]


def test_plain_handles_nested_math_readably(vault_root):
    """--plain 不应把常见嵌套公式转坏。"""
    _make_card(
        vault_root,
        "nested-card.md",
        TODAY,
        2,
        question_lines=["- 求 $\\left(\\frac{x+1}{x-1}\\right)^2$ 的值。"],
        option_lines=["- A. $\\sqrt{1+\\frac{1}{x}}$"],
    )
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY, "--plain"])
    assert rc == 0
    data = json.loads(out)
    item = next(card for card in data["due"] if card["filename"] == "nested-card")
    assert "\\right" not in item["question_text"]
    assert "\\frac" not in item["options_text"]
    assert "≤ft" not in item["question_text"]
    assert "((x+1)/(x-1))²" in item["question_text"]
    assert "√(1+1/x)" in item["question_text"]
    assert "√(1+1/x)" in item["options_text"]


def test_question_figure_embed_is_replaced_in_cli_preview(vault_root):
    """CLI 预览里不该出现 `![[...svg]]`：那玩意只有 Obsidian 渲染得出来。"""
    _make_card(
        vault_root,
        "with-figure.md",
        TODAY,
        2,
        question_lines=[
            "- 如图所示的电路，求等效电阻。",
            "",
            "![[错题本/_附图/qid-000000000001/qid-000000000001-01-电路.svg|480]]",
            "- 图1：题面所给电路",
            "![[错题本/_附图/qid-000000000001/qid-000000000001-02-等效.svg|480]]",
            "- 图2：等效变换后",
        ],
    )
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY, "--plain"])
    assert rc == 0
    card = json.loads(out)["due"][0]
    for field in ("question_text", "question_preview"):
        assert "![[" not in card[field], card[field]
        assert "（本题有配图，请在 Obsidian 中查看）" in card[field]
    # 连续两张图只提示一次，别把预览占满
    assert card["question_text"].count("（本题有配图，请在 Obsidian 中查看）") == 2
    assert "如图所示的电路" in card["question_text"]


def test_code_block_figures_are_replaced_in_cli_preview(vault_root):
    """tikz / mermaid 代码块在 CLI 里是满屏源码，和 svg 嵌入一样换成一句提示。"""
    _make_card(
        vault_root,
        "with-code-figure.md",
        TODAY,
        2,
        question_lines=[
            "- 如图所示的数据通路，写出取指周期的微操作。",
            "",
            "%%图源：错题本/_附图/qid-000000000002/qid-000000000002-01-通路.mmd%%",
            "```mermaid",
            "flowchart LR",
            '  PC["PC"] -->|"PCout=1"| MAR["MAR"]',
            "```",
            "- 图1：题面所给数据通路",
            "```tikz",
            "\\begin{document}\\begin{tikzpicture}\\draw (0,0)--(1,1);\\end{tikzpicture}\\end{document}",
            "```",
            "- 图2：立体",
        ],
    )
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY, "--plain"])
    assert rc == 0
    card = json.loads(out)["due"][0]
    for field in ("question_text", "question_preview"):
        assert "```" not in card[field], card[field]
        assert "%%图源" not in card[field], card[field]
        assert "flowchart" not in card[field], card[field]
    assert card["question_text"].count("（本题有配图，请在 Obsidian 中查看）") == 2
    assert "如图所示的数据通路" in card["question_text"]
    assert "- 图1：题面所给数据通路" in card["question_text"]
