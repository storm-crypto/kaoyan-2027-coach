"""test update_knowledge_map.py"""
import json
import textwrap
import pytest
from helpers import run_script


def test_single_match(knowledge_map, vault_root):
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "半会", "极坐标不熟"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["updated"] == "05.5 二重积分"
    assert data["mastery"] == "半会"
    # 验证文件已更新
    content = (knowledge_map / "数学一.md").read_text()
    assert "半会" in content


def test_no_match(knowledge_map, vault_root):
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "不存在的考点", "会"
    ])
    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True


def test_ambiguous_match(knowledge_map, vault_root):
    """多行匹配应报错并列出候选。"""
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "积分", "会"
    ])
    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True
    assert "candidates" in data


def test_chapter_header_skipped(knowledge_map, vault_root):
    """章节标题（含 **）不应被匹配。"""
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "多元函数微积分", "会"
    ])
    assert rc == 1  # 章节标题被跳过，所以找不到叶子行


def test_unknown_subject(knowledge_map, vault_root):
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "物理", "力学", "会"
    ])
    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True


def test_env_var(knowledge_map, vault_root):
    rc, out, _ = run_script("update_knowledge_map.py", [
        "数学一", "三重积分", "不会"
    ], env_extra={"KAOYAN_OBSIDIAN_ROOT": str(vault_root)})
    assert rc == 0
    data = json.loads(out)
    assert data["mastery"] == "不会"


@pytest.fixture
def lilang_knowledge_map(vault_root):
    """李林结构的数学一知识地图，覆盖 alias 命中所需的几个章节。"""
    km_dir = vault_root / "知识地图"
    content = textwrap.dedent("""\
        ## 高等数学 (约 56%)
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **01 第一章 函数、极限、连续** | | | |
        | 01.01 第一节 函数 | | | |
        | 01.02 第二节 函数极限 | | | |
        | 01.03 第三节 数列极限 | | | |
        | 01.04 第四节 函数的连续性 | | | |
        | **10 第十章 二重积分** | | | |
        | 10.02 第二节 二重积分的计算 | | | |

        ## 线性代数 (约 22%)
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **04 第四章 线性方程组** | | | |
        | 04.01 第一节 齐次线性方程组 | | | |
        | 04.02 第二节 非齐次线性方程组 | | | |
        | 04.03 第三节 线性方程组的综合应用 | | | |
    """)
    (km_dir / "数学一.md").write_text(content, encoding="utf-8")
    return km_dir


def test_alias_old_bucket_resolves_to_new_leaf(lilang_knowledge_map, vault_root):
    """传入旧通用桶名应通过 alias 命中新李林叶子行。"""
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "函数的性质与图形", "不会", "周期性不稳"
    ])
    assert rc == 0, out
    data = json.loads(out)
    assert data["updated"] == "01.01 第一节 函数"
    assert data["mastery"] == "不会"
    content = (lilang_knowledge_map / "数学一.md").read_text()
    assert "周期性不稳" in content


def test_alias_new_leaf_name_still_works(lilang_knowledge_map, vault_root):
    """传入新李林叶子精确名应直接命中（alias 不命中时透传）。"""
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "01.03 第三节 数列极限", "半会"
    ])
    assert rc == 0, out
    data = json.loads(out)
    assert data["updated"] == "01.03 第三节 数列极限"
    assert data["mastery"] == "半会"


def test_alias_split_linear_equations_three_leaves(lilang_knowledge_map, vault_root):
    """线代第四章 alias 拆分后，齐次/非齐次/综合应用三条都能命中各自叶子。"""
    rc1, out1, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "齐次方程组", "不会"
    ])
    rc2, out2, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "非齐次方程组", "半会"
    ])
    rc3, out3, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "方程组综合应用", "会"
    ])
    assert (rc1, rc2, rc3) == (0, 0, 0)
    assert json.loads(out1)["updated"] == "04.01 第一节 齐次线性方程组"
    assert json.loads(out2)["updated"] == "04.02 第二节 非齐次线性方程组"
    assert json.loads(out3)["updated"] == "04.03 第三节 线性方程组的综合应用"


def test_write_back_keeps_clean_pipe_spacing(lilang_knowledge_map, vault_root):
    """写回后表格行应保持 `| cell | cell | cell | cell |` 干净格式，
    不能产生 `|topic| 不会 ||  note |` 这种连续 pipe 或缺失两侧空格的行。"""
    rc, _, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "数列极限", "半会", "测试备注"
    ])
    assert rc == 0
    content = (lilang_knowledge_map / "数学一.md").read_text(encoding="utf-8")
    target_line = next(line for line in content.splitlines() if "01.03 第三节 数列极限" in line)
    assert target_line == "| 01.03 第三节 数列极限 | 半会 |  | 测试备注 |"


# ---- 结构化卡点（finding）模式 ----

def _make_wrong_card(vault_root, qid, interval, last_review="2026-05-14"):
    """在错题本里造一张数学一卡片，给 sync_mastered_status 用。"""
    card_dir = vault_root / "错题本" / "数学一" / "高等数学"
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / f"test-{qid}.md"
    card.write_text(textwrap.dedent(f"""\
        ---
        source: 测试
        question_id: {qid}
        topic: 测试
        error_tags: []
        first_wrong_at: 2026-04-01
        last_review_at: {last_review}
        wrong_count: 1
        status: 不会
        next_review: 2026-05-15
        review_interval: {interval}
        ease_factor: 2.50
        ---

        #subject/math1

        ## 测试
    """), encoding="utf-8")
    return card


def test_finding_add_single(knowledge_map, vault_root):
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "半会",
        "--finding-add", "qid-aaaa11112222|2026-05-14|极坐标变换上下限搞反",
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["finding_count"] == 1
    assert data["mastered_count"] == 0
    content = (knowledge_map / "数学一.md").read_text(encoding="utf-8")
    target_line = next(line for line in content.splitlines() if "05.5 二重积分" in line)
    assert "[2026-05-14] 极坐标变换上下限搞反 (qid-aaaa11112222)" in target_line
    assert "1." in target_line


def test_finding_add_multiple(knowledge_map, vault_root):
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "半会",
        "--finding-add", "qid-aaaa11112222|2026-05-01|卡点A",
        "--finding-add", "qid-bbbb22223333|2026-05-10|卡点B",
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["finding_count"] == 2
    content = (knowledge_map / "数学一.md").read_text(encoding="utf-8")
    target_line = next(line for line in content.splitlines() if "05.5 二重积分" in line)
    assert "1. [2026-05-01] 卡点A (qid-aaaa11112222)" in target_line
    assert "2. [2026-05-10] 卡点B (qid-bbbb22223333)" in target_line


def test_finding_add_dedups_by_qid(knowledge_map, vault_root):
    """同 qid 二次 --finding-add 应该更新描述、不新增条目。"""
    run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "半会",
        "--finding-add", "qid-aaaa11112222|2026-05-01|老描述",
    ])
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "半会",
        "--finding-add", "qid-aaaa11112222|2026-05-14|新描述更准确",
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["finding_count"] == 1
    content = (knowledge_map / "数学一.md").read_text(encoding="utf-8")
    target_line = next(line for line in content.splitlines() if "05.5 二重积分" in line)
    assert "新描述更准确" in target_line
    assert "老描述" not in target_line
    # first_exposed 保留首次的 2026-05-01，不是更新成 2026-05-14
    assert "[2026-05-01]" in target_line


def test_finding_add_legacy_note_dropped_by_default(knowledge_map, vault_root):
    """老的自由文本备注在首次 --finding-add 时默认丢弃。"""
    # 先用旧用法写入一段自由文本
    run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "半会", "一段乱写的老备注随便发挥的内容"
    ])
    # 再用 finding 模式写入
    rc, _, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "半会",
        "--finding-add", "qid-aaaa11112222|2026-05-14|新卡点",
    ])
    assert rc == 0
    content = (knowledge_map / "数学一.md").read_text(encoding="utf-8")
    target_line = next(line for line in content.splitlines() if "05.5 二重积分" in line)
    assert "新卡点" in target_line
    assert "乱写的老备注" not in target_line


def test_finding_add_keep_legacy_note(knowledge_map, vault_root):
    run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "半会", "想留下的老备注"
    ])
    rc, _, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "半会",
        "--finding-add", "qid-aaaa11112222|2026-05-14|新卡点",
        "--keep-legacy-note",
    ])
    assert rc == 0
    content = (knowledge_map / "数学一.md").read_text(encoding="utf-8")
    target_line = next(line for line in content.splitlines() if "05.5 二重积分" in line)
    assert "新卡点" in target_line
    assert "想留下的老备注" in target_line


def test_finding_sync_auto_strikes_when_interval_ge_threshold(knowledge_map, vault_root):
    """对应错题卡 review_interval ≥ 14 时，重跑脚本应自动划掉对应 finding。"""
    _make_wrong_card(vault_root, "qid-aaaa11112222", interval=20, last_review="2026-05-14")
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "会",
        "--finding-add", "qid-aaaa11112222|2026-04-01|本来不会现在掌握",
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["mastered_count"] == 1
    content = (knowledge_map / "数学一.md").read_text(encoding="utf-8")
    target_line = next(line for line in content.splitlines() if "05.5 二重积分" in line)
    assert "~~[2026-04-01 → 2026-05-14] 本来不会现在掌握 (qid-aaaa11112222)~~" in target_line


def test_finding_sync_does_not_strike_below_threshold(knowledge_map, vault_root):
    _make_wrong_card(vault_root, "qid-aaaa11112222", interval=5, last_review="2026-05-14")
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "不会",
        "--finding-add", "qid-aaaa11112222|2026-05-01|还卡着",
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["mastered_count"] == 0
    content = (knowledge_map / "数学一.md").read_text(encoding="utf-8")
    target_line = next(line for line in content.splitlines() if "05.5 二重积分" in line)
    assert "~~" not in target_line


def test_finding_fold_threshold_triggers_details_block(knowledge_map, vault_root):
    """已掌握 ≥ fold_threshold 时应包 <details>。"""
    # 4 张已掌握的卡（interval=30）+ 1 张未掌握的（interval=2）
    qids_mastered = ["qid-aa11aa11aa11", "qid-bb22bb22bb22", "qid-cc33cc33cc33", "qid-dd44dd44dd44"]
    for qid in qids_mastered:
        _make_wrong_card(vault_root, qid, interval=30, last_review="2026-05-14")
    _make_wrong_card(vault_root, "qid-ee55ee55ee55", interval=2, last_review="2026-05-14")

    args = [str(vault_root), "数学一", "二重积分", "会"]
    for i, qid in enumerate(qids_mastered):
        args.extend(["--finding-add", f"{qid}|2026-04-0{i+1}|已掌握{i+1}"])
    args.extend(["--finding-add", "qid-ee55ee55ee55|2026-05-10|还卡着"])

    rc, out, _ = run_script("update_knowledge_map.py", args)
    assert rc == 0
    data = json.loads(out)
    assert data["mastered_count"] == 4
    content = (knowledge_map / "数学一.md").read_text(encoding="utf-8")
    target_line = next(line for line in content.splitlines() if "05.5 二重积分" in line)
    assert "<details><summary>已掌握 4 条</summary>" in target_line
    assert "</details>" in target_line
    # 未掌握的在 details 外面
    details_pos = target_line.find("<details>")
    yikazhe_pos = target_line.find("还卡着")
    assert 0 <= yikazhe_pos < details_pos


def test_finding_sync_runs_even_without_finding_add(knowledge_map, vault_root):
    """已经有 findings 的考点，再次调用脚本（不带 --finding-add）也应触发 sync。"""
    # 第一次：建一条未划的 finding，对应的卡 interval=5（未到阈值）
    _make_wrong_card(vault_root, "qid-aaaa11112222", interval=5, last_review="2026-05-01")
    run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "不会",
        "--finding-add", "qid-aaaa11112222|2026-04-01|新卡点",
    ])
    # 第二次：错题卡 interval 已经长到 18，不带新 finding，只是想触发同步划掉
    _make_wrong_card(vault_root, "qid-aaaa11112222", interval=18, last_review="2026-05-14")
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "会"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["mastered_count"] == 1
    content = (knowledge_map / "数学一.md").read_text(encoding="utf-8")
    target_line = next(line for line in content.splitlines() if "05.5 二重积分" in line)
    assert "~~[2026-04-01 → 2026-05-14] 新卡点 (qid-aaaa11112222)~~" in target_line


def test_finding_add_invalid_format_returns_error(knowledge_map, vault_root):
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "半会",
        "--finding-add", "格式不对",
    ])
    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True
    assert "格式错误" in data["message"]
