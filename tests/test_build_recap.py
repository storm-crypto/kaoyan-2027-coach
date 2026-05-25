"""test build_recap.py (周复盘 + 月复盘)"""
import json
import textwrap

from helpers import run_script


def _write_log(vault_root, day, hours, learned, blocker, scores=None):
    log_path = vault_root / "学习日志" / f"{day}.md"
    score_section = "## 训练成绩记录\n- 今天没有单独记录训练成绩。\n"
    if scores:
        rows = [
            "## 训练成绩记录",
            "| 科目 | 类型 | 来源 | 得分 | 满分 | 完成率 | 备注 |",
            "|------|------|------|------|------|--------|------|",
        ]
        for score in scores:
            rows.append(
                f"| {score['subject']} | {score['kind']} | {score['source']} | "
                f"{score['score']} | {score['total']} | {score['rate']} | {score['note']} |"
            )
        score_section = "\n".join(rows) + "\n"
    log_path.write_text(textwrap.dedent(f"""\
        # Session: {day}

        ## 今日概览
        - **主题**: 数学 + 408
        - **时长**: {hours}
        - **模式**: 错题解析 / 复习

        ## 学到了什么
        - {learned}

        ## 卡壳与挣扎
        - {blocker}

        {score_section}
    """), encoding="utf-8")


def _write_review_card(vault_root, history_dates):
    card = vault_root / "错题本" / "数学一" / "高等数学" / "review-card.md"
    history_lines = "\n".join(f"- {d} - 半会 - 复习中" for d in history_dates)
    content = (
        "---\n"
        "source: test\n"
        "question_id: qid-weekreview1\n"
        "topic: 二重积分\n"
        "first_wrong_at: 2026-03-01\n"
        "last_review_at: 2026-03-18\n"
        "wrong_count: 2\n"
        "status: 半会\n"
        "next_review: 2026-03-21\n"
        "review_interval: 3\n"
        "ease_factor: 2.50\n"
        "---\n"
        "\n"
        "### 历史记录\n"
        f"{history_lines}\n"
    )
    card.write_text(content, encoding="utf-8")


def _write_chapter_report(vault_root, day, module, chapter, mastery, unstable, illusion, gap):
    report_dir = vault_root / "章节掌握报告" / "408" / module
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{day}-{chapter}.md"
    report_path.write_text(textwrap.dedent(f"""\
        ---
        type: chapter_grill_report
        subject: 408
        module: {module}
        chapter: {chapter}
        session_date: {day}
        source: gemini-voyager
        import_confidence: high
        overall_mastery: {mastery}
        knowledge_map_updated: 1
        knowledge_map_skipped: 0
        ---

        # 章节掌握报告：{chapter}

        ## 半会但不稳的点
        - {unstable}

        ## 不会或有能力错觉的点
        - {illusion}

        ## 关键漏洞
        - {gap}
    """), encoding="utf-8")


def test_week_recap(vault_root):
    """周复盘：扫描本周一到周日的日志和错题卡历史。"""
    _write_log(
        vault_root,
        "2026-03-16",
        4,
        "数学二重积分拆清楚了",
        "408 进程调度还是容易混",
        scores=[{
            "subject": "数学一",
            "kind": "真题",
            "source": "2024 数学一真题",
            "score": "138",
            "total": "150",
            "rate": "92.0%",
            "note": "计算有点急",
        }],
    )
    _write_log(
        vault_root,
        "2026-03-18",
        3.5,
        "英语阅读定位更快了",
        "数学计算还是会慌",
        scores=[{
            "subject": "数学一",
            "kind": "真题",
            "source": "2025 数学一真题",
            "score": "145",
            "total": "150",
            "rate": "96.7%",
            "note": "整体更稳",
        }],
    )
    _write_review_card(vault_root, ["2026-03-17", "2026-03-19"])

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["period"] == "week"
    assert data["label"] == "2026-W12"
    assert data["logged_days"] == 2
    assert data["review_count"] == 2
    assert data["score_count"] == 2
    output_path = vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "7.5 小时" in content
    assert "数学" in content
    assert "## 成绩趋势" in content
    assert "数学一·真题：2 次，首次 138/150，最近 145/150，最高 145/150" in content


def test_week_recap_default_period(vault_root):
    """不传 --period 默认就是周复盘。"""
    _write_log(vault_root, "2026-03-16", 2, "学了点东西", "没啥卡点")

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["period"] == "week"


def test_month_recap(vault_root):
    """月复盘：扫描当月 1 日到月末的日志和错题卡历史。"""
    # 写 3 月的多天日志
    _write_log(vault_root, "2026-03-05", 3, "数学极限搞懂了", "408 还是有点乱")
    _write_log(vault_root, "2026-03-12", 4, "线性代数开始有感觉", "政治马原太绕")
    _write_log(
        vault_root,
        "2026-03-20",
        5,
        "英语阅读提速",
        "数学积分还需练",
        scores=[{
            "subject": "英语一",
            "kind": "阅读",
            "source": "张剑阅读 08",
            "score": "17",
            "total": "20",
            "rate": "85.0%",
            "note": "第四篇两题犹豫",
        }],
    )
    _write_review_card(vault_root, ["2026-03-05", "2026-03-12", "2026-03-20"])

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "month", "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["period"] == "month"
    assert data["label"] == "2026年03月"
    assert data["logged_days"] == 3
    assert data["review_count"] == 3
    assert data["score_count"] == 1
    assert "2026-03-01 ~ 2026-03-31" in data["date_range"]
    output_path = vault_root / "复盘报告" / "2026-03-月复盘.md"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "12 小时" in content
    assert "# 月复盘：2026年03月" in content
    assert "## 本月概览" in content
    assert "## 成绩趋势" in content
    assert "## 下月建议" in content


def test_month_recap_empty(vault_root):
    """月复盘：没有任何日志和错题也不报错。"""
    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "month", "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["logged_days"] == 0
    assert data["review_count"] == 0


def test_week_recap_supports_legacy_indented_score_heading(vault_root):
    log_path = vault_root / "学习日志" / "2026-03-16.md"
    log_path.write_text(textwrap.dedent("""\
        # Session: 2026-03-16

        ## 今日概览
        - **主题**: 数学
        - **时长**: 2

          ## 训练成绩记录
          | 科目 | 类型 | 来源 | 得分 | 满分 | 完成率 | 备注 |
          |------|------|------|------|------|--------|------|
          | 数学一 | 真题 | 2024 数学一真题 | 138 | 150 | 92.0% | legacy heading |
    """), encoding="utf-8")

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["score_count"] == 1


def test_week_recap_includes_subject_score_tables(sample_archive, vault_root):
    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["score_count"] == 2
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    assert "数学一·模拟：1 次，最近 105/150，完成率 70.0%。" in content
    assert "408·模拟：1 次，最近 101/150，完成率 67.3%。" in content


def test_week_recap_includes_chapter_grill_reports(vault_root):
    _write_log(vault_root, "2026-03-18", 2, "计组看了一章", "Cache 还是混")
    _write_chapter_report(
        vault_root,
        "2026-03-19",
        "计算机组成原理",
        "01-计算机系统概述",
        "半会",
        "性能指标的推理链条不稳",
        "Cache 只有口头印象，没有机制图景",
        "CPU 时间和 CPI 关系总说反",
    )

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["period"] == "week"
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    assert "## 章节诊断" in content
    assert "本周新增 1 份章节掌握报告" in content
    assert "计算机组成原理 1 章" in content
    assert "CPU 时间和 CPI 关系总说反" in content


def test_week_recap_dedupes_progress_score_and_subject_table(sample_archive, vault_root):
    rc, _, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", "2026-03-23",
        "--topic", "数学真题训练",
        "--score", "数学一|真题训练|2009年真题|145|150|中值定理不太会",
        "--subject-score", "数学一|2009年真题|145|中值定理不太会|",
    ])

    assert rc == 0

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-23"
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["score_count"] == 1
    content = (vault_root / "复盘报告" / "2026-W13-0323-0329-周复盘.md").read_text(encoding="utf-8")
    assert "数学一·真题训练：1 次，最近 145/150，完成率 96.7%。" in content


def _write_note(vault_root, rel_path, created):
    path = vault_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ncreated: {created}\n---\n正文\n", encoding="utf-8")
    return path


def _write_wrong_card(vault_root, subject, chapter_dir, name, first_wrong_at, history):
    """工具：建一张错题卡，history 是 [(date, status)] 列表。"""
    card_dir = vault_root / "错题本" / subject / "高等数学" / chapter_dir
    card_dir.mkdir(parents=True, exist_ok=True)
    card_path = card_dir / f"{name}.md"
    history_lines = "\n".join(f"- {d} - {s} - 测试" for d, s in history)
    card_path.write_text(
        f"---\n"
        f"source: test\n"
        f"question_id: qid-{name}\n"
        f"topic: {name}\n"
        f"first_wrong_at: {first_wrong_at}\n"
        f"last_review_at: {history[-1][0] if history else first_wrong_at}\n"
        f"status: 不会\n"
        f"---\n\n"
        f"### 历史记录\n"
        f"{history_lines}\n",
        encoding="utf-8",
    )


def test_week_recap_includes_note_stats_section(vault_root):
    _write_note(vault_root, "知识笔记/数学一/高数/ch1 函数 极限 连续/Stolz 定理.md", "2026-03-18")
    _write_note(vault_root, "知识笔记/数学一/高数/ch3 微分中值定理与泰勒公式/双中值.md", "2026-03-19")

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["note_count"] == 2
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    assert "## 知识沉淀" in content
    assert "本周共新增 2 篇笔记" in content
    assert "数学一 2 篇" in content


def test_week_recap_only_drilling_warning(vault_root):
    # 第3章 4 张新错题 + 笔记 0 篇 → only-drilling
    for i in range(4):
        _write_wrong_card(
            vault_root,
            "数学一",
            "03第三章微分中值定理与泰勒公式",
            f"card_{i}",
            "2026-03-17",
            [("2026-03-17", "不会")],
        )
    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["only_drilling_count"] >= 1
    assert data["new_wrong_count"] == 4
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    assert "## 错题暴露" in content
    assert "本周新增错题 4 道" in content
    assert "## 知识沉淀 × 错题暴露" in content
    assert "only-drilling" in content
    assert "数学一·高等数学·第3章" in content


def test_week_recap_only_theory_warning(vault_root):
    _write_note(vault_root, "知识笔记/数学一/高数/ch5 不定积分/A.md", "2026-03-18")
    _write_note(vault_root, "知识笔记/数学一/高数/ch5 不定积分/B.md", "2026-03-19")
    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["only_theory_count"] >= 1
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    assert "only-theory" in content


def test_week_recap_stubborn_card_top(vault_root):
    _write_wrong_card(
        vault_root,
        "数学一",
        "06第六章定积分及其应用",
        "fail_a",
        "2026-03-01",
        [("2026-03-17", "不会"), ("2026-03-19", "不会"), ("2026-03-20", "不会")],
    )
    rc, _, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    assert "顽固卡 TOP" in content
    assert "fail_a" in content


def test_month_recap_includes_coverage_section(vault_root):
    (vault_root / "知识地图").mkdir(exist_ok=True)
    (vault_root / "知识地图" / "数学一.md").write_text(
        "## 高等数学\n"
        "| a |\n|---|\n"
        "| **01 第一章 函数、极限、连续** | |\n"
        "| **03 第三章 微分中值定理与泰勒公式** | |\n"
        "| **05 第五章 不定积分** | |\n",
        encoding="utf-8",
    )
    _write_note(vault_root, "知识笔记/数学一/高数/ch1 函数 极限 连续/A.md", "2026-03-18")
    _write_wrong_card(
        vault_root,
        "数学一",
        "03第三章微分中值定理与泰勒公式",
        "card_x",
        "2026-03-17",
        [("2026-03-17", "不会")],
    )

    rc, _, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "month", "--today", "2026-03-20"
    ])
    assert rc == 0
    content = (vault_root / "复盘报告" / "2026-03-月复盘.md").read_text(encoding="utf-8")
    assert "## 知识地图覆盖" in content
    assert "数学一：共 3 章" in content
    assert "笔记覆盖 1/3" in content
    assert "错题覆盖 1/3" in content
    assert "第5章 不定积分" in content  # blank chapter


def _write_wrong_card_in(vault_root, rel_dir, name, first_wrong_at, history):
    """更通用的错题卡写入：rel_dir 是相对 错题本/ 的目录段（可包含或不包含 subgroup）。"""
    card_dir = vault_root / "错题本" / rel_dir
    card_dir.mkdir(parents=True, exist_ok=True)
    card_path = card_dir / f"{name}.md"
    history_lines = "\n".join(f"- {d} - {s} - 测试" for d, s in history)
    card_path.write_text(
        f"---\n"
        f"source: test\n"
        f"question_id: qid-{name}\n"
        f"topic: {name}\n"
        f"first_wrong_at: {first_wrong_at}\n"
        f"last_review_at: {history[-1][0] if history else first_wrong_at}\n"
        f"status: 不会\n"
        f"---\n\n"
        f"### 历史记录\n"
        f"{history_lines}\n",
        encoding="utf-8",
    )


def test_cross_signals_no_collision_across_subgroups(vault_root):
    """高数 ch1 和 线代 ch1 章节号都为 1，但属于不同 subgroup，不应被合并成同一信号。"""
    # 高数 ch1: 4 张新错题 → only-drilling
    for i in range(4):
        _write_wrong_card_in(
            vault_root,
            "数学一/高等数学/01 第一章 函数、极限、连续/01 第一节 函数",
            f"gaoshu_{i}",
            "2026-03-17",
            [("2026-03-17", "不会")],
        )
    # 线代 ch1: 0 错题 + 2 篇笔记 → only-theory
    _write_note(vault_root, "知识笔记/数学一/线代/ch1 行列式/A.md", "2026-03-18")
    _write_note(vault_root, "知识笔记/数学一/线代/ch1 行列式/B.md", "2026-03-19")

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    # 两个不同子科目的 ch1 都应该出现，不被合并
    assert data["only_drilling_count"] >= 1
    assert data["only_theory_count"] >= 1
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    assert "数学一·高等数学·第1章" in content
    assert "数学一·线性代数·第1章" in content


def test_coverage_no_collision_across_subgroups(vault_root):
    """知识地图里多个子科目都有 ch1，覆盖度统计不能把它们合并。"""
    (vault_root / "知识地图").mkdir(exist_ok=True)
    (vault_root / "知识地图" / "数学一.md").write_text(
        "## 高等数学\n| a |\n|---|\n| **01 第一章 函数、极限、连续** | |\n"
        "## 线性代数\n| a |\n|---|\n| **01 第一章 行列式** | |\n",
        encoding="utf-8",
    )
    # 只在高数 ch1 写笔记
    _write_note(vault_root, "知识笔记/数学一/高数/ch1 函数 极限 连续/A.md", "2026-03-18")

    rc, _, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "month", "--today", "2026-03-20"
    ])
    assert rc == 0
    content = (vault_root / "复盘报告" / "2026-03-月复盘.md").read_text(encoding="utf-8")
    # 数学一共 2 章；只有高数 ch1 有笔记
    assert "数学一：共 2 章" in content
    assert "笔记覆盖 1/2" in content
    # 线代 ch1 应该出现在空白列表里
    assert "线性代数·第1章" in content


def test_408_bare_chapter_naming_parses(vault_root):
    """408 知识地图用 `01 线性表` 格式，要能解析到 chapter_num=1 并参与统计。"""
    (vault_root / "知识地图").mkdir(exist_ok=True)
    (vault_root / "知识地图" / "408.md").write_text(
        "## 数据结构\n| a |\n|---|\n"
        "| **01 线性表** | |\n"
        "| **03 树与二叉树** | |\n",
        encoding="utf-8",
    )
    # 错题路径用相同 bare 命名（无 subgroup）
    _write_wrong_card_in(
        vault_root,
        "408/01 线性表",
        "card_408",
        "2026-03-17",
        [("2026-03-17", "不会"), ("2026-03-18", "不会"), ("2026-03-19", "不会")],
    )

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "month", "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    # 错题路径里 chapter 能解出来 → 应作为新增 + 顽固计入
    assert data["new_wrong_count"] == 1
    assert data["stubborn_count"] >= 1
    content = (vault_root / "复盘报告" / "2026-03-月复盘.md").read_text(encoding="utf-8")
    # 知识地图覆盖里：408 共 2 章，错题覆盖 1/2
    assert "408：共 2 章" in content
    assert "错题覆盖 1/2" in content
    # 空白章应出现 03 树与二叉树
    assert "树与二叉树" in content


def test_wrong_card_path_without_subgroup(vault_root):
    """错题路径 `错题本/{科目}/{章节}/{file}` (无 subgroup) 时章节解析仍要工作。"""
    _write_wrong_card_in(
        vault_root,
        "数学一/03第三章微分中值定理与泰勒公式",
        "no_subgroup",
        "2026-03-17",
        [("2026-03-17", "不会"), ("2026-03-19", "不会")],
    )

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    # 路径解析正确则会进入 stubborn (fail_in_range >= 2)
    assert data["stubborn_count"] >= 1
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    assert "第3章" in content
    # 不能把 `no_subgroup.md` 错当成章节
    assert "no_subgroup.md" not in content


def _write_log_with_structured_bullets(vault_root, day, learned, blockers):
    log_path = vault_root / "学习日志" / f"{day}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    learned_section = "\n".join(f"- {x}" for x in learned) if learned else "_（今天没有显式记录。）_"
    blocker_section = "\n".join(f"- {x}" for x in blockers) if blockers else "_（今天没有显式记录卡点。）_"
    log_path.write_text(
        f"# Session: {day}\n\n"
        f"## 今日概览\n- **主题**: 测试\n- **时长**: 3\n- **模式**: 测试\n\n"
        f"## 学到了什么\n{learned_section}\n\n"
        f"## 卡壳与挣扎\n{blocker_section}\n\n"
        f"## 训练成绩记录\n- 今天没有单独记录训练成绩。\n",
        encoding="utf-8",
    )


def test_recap_filters_placeholder_bullets_from_legacy_logs(vault_root):
    """老日志里残留的「今天没有显式记录卡点。」不应当作真实数据抓回来。"""
    log_path = vault_root / "学习日志" / "2026-03-18.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "# Session: 2026-03-18\n\n"
        "## 学到了什么\n- 今天的收获还比较散，建议明天补成更具体的知识点。\n\n"
        "## 卡壳与挣扎\n"
        "- 今天没有显式记录卡点。\n"
        "- 今天没有显式记录卡点。\n"
        "- 反函数二阶求导题型识别不稳\n\n"
        "## 训练成绩记录\n- 今天没有单独记录训练成绩。\n",
        encoding="utf-8",
    )
    rc, _, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    # 占位符不能出现在卡点段
    assert "今天没有显式记录卡点。" not in content
    # 「下周建议」也不能照搬占位符
    assert "优先拆解：今天没有显式记录卡点" not in content
    # 真正的卡点应该被保留
    assert "反函数二阶求导题型识别不稳" in content


def test_recap_renders_date_prefix_on_blockers(vault_root):
    """卡点行应带 [MM-DD] 日期戳。"""
    _write_log_with_structured_bullets(
        vault_root, "2026-03-18", [], ["卡点::反函数二阶求导 (数学一·高数·ch2)"],
    )
    rc, _, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    assert "[03-18]" in content
    assert "反函数二阶求导" in content
    assert "数学一·高等数学·第2章" in content


def test_recap_aggregates_highlights_by_chapter(vault_root):
    """学习产出应该按章节聚类，而不是按日期堆叠。"""
    _write_log_with_structured_bullets(
        vault_root, "2026-03-16",
        ["学习::分段函数可导性 (数学一·高数·ch2)", "学习::导数与微分计算 (数学一·高数·ch2)"], [],
    )
    _write_log_with_structured_bullets(
        vault_root, "2026-03-18",
        ["学习::中值定理三大变体 (数学一·高数·ch3)"], [],
    )
    rc, _, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    # 章节聚合 key 用 normalized subgroup（高数→高等数学）
    assert "数学一·高等数学·第2章" in content
    assert "2 条事件" in content
    assert "[03-16] 学习: 分段函数可导性" in content


def test_recap_aggregates_textbook_progress(vault_root):
    _write_log_with_structured_bullets(
        vault_root, "2026-03-16",
        ["教材::李林高数 推进到 p48 (数学一·高数·ch2)"], [],
    )
    _write_log_with_structured_bullets(
        vault_root, "2026-03-18",
        ["教材::李林高数 推进到 p56 (数学一·高数·ch2)"], [],
    )
    rc, _, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    assert "教材进度" in content
    assert "李林高数" in content
    assert "p48 → p56" in content


def test_recap_stubborn_card_uses_wikilink(vault_root):
    _write_wrong_card_in(
        vault_root,
        "数学一/高等数学/03第三章微分中值定理与泰勒公式",
        "fail_card",
        "2026-03-01",
        [("2026-03-17", "不会"), ("2026-03-19", "不会"), ("2026-03-20", "不会")],
    )
    rc, _, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    # wikilink 形式：[[路径|显示名]]
    assert "[[错题本/数学一/高等数学/03第三章微分中值定理与泰勒公式/fail_card|fail_card]]" in content


def test_recap_next_actions_data_driven(vault_root):
    """下周建议应基于实际数据，不能全是模板兜底。"""
    # 造一个 only-drilling 场景：5 张新错题 + 0 篇笔记
    for i in range(5):
        _write_wrong_card_in(
            vault_root,
            "数学一/高等数学/03第三章微分中值定理与泰勒公式",
            f"card_{i}",
            "2026-03-17",
            [("2026-03-17", "不会")],
        )
    rc, _, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    assert "## 下周建议" in content
    # 建议要点名具体章节并给出数字
    assert "数学一" in content and "第3章" in content
    # wrong_score = new(5) + fail(5) = 10 → "已积 10 道错题但 0 篇笔记"
    assert "已积 10 道错题但 0 篇笔记" in content
    # 不应再出现万年模板
    assert "下周继续给 数学一 留整块时间" not in content


def test_recap_highlights_group_by_day_does_not_truncate(vault_root):
    """无章节标签的自然语言 bullet 应按天分组展开，不再 [:4] 截断。"""
    # 模拟用户的原始日志：6 天，每天 1-3 条无标签自然语言 bullet
    daily_bullets = {
        "2026-03-16": ["开始过李林辅导讲义", "做了几道极限题", "线代行列式入门"],
        "2026-03-17": ["完成李林讲义 ch1 习题"],
        "2026-03-18": ["复习了泰勒展开例题", "做了一套真题"],
        "2026-03-19": ["错题归档 8 道", "整理中值定理笔记"],
        "2026-03-20": ["做了一个英语阅读专项"],
        "2026-03-21": ["休息一天"],
    }
    for day, bullets in daily_bullets.items():
        _write_log_with_structured_bullets(vault_root, day, bullets, [])

    rc, _, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-22"
    ])
    assert rc == 0
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    # 「逐日产出」段必须出现
    assert "逐日产出" in content
    # 每天的 bullet 都得展示，不再丢
    assert "做了几道极限题" in content
    assert "线代行列式入门" in content
    assert "做了一个英语阅读专项" in content
    assert "休息一天" in content
    # 每个日期戳都得出现
    for day in daily_bullets:
        month, day_num = day.split("-")[1], day.split("-")[2]
        assert f"[{month}-{day_num}]" in content


def test_recap_highlights_caps_per_day_with_fold_hint(vault_root):
    """单日 > 8 条时折叠尾部并展示"还有 N 条"提示。"""
    # 一天造 12 条 bullet
    many_bullets = [f"自然语言条目 {i+1}" for i in range(12)]
    _write_log_with_structured_bullets(vault_root, "2026-03-16", many_bullets, [])

    rc, _, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    # 前 8 条可见
    assert "自然语言条目 1" in content
    assert "自然语言条目 8" in content
    # 第 9-12 条不直接出现
    assert "自然语言条目 12" not in content
    # 但有折叠提示
    assert "还有 4 条已折叠" in content


def test_recap_highlights_inferred_chapter_lifts_bullet_into_cluster(vault_root):
    """带「李林高数 + 中值定理」关键词的 bullet 应被推到 数学一·高等数学·第3章 聚类，不进逐日产出。"""
    _write_log_with_structured_bullets(
        vault_root, "2026-03-16",
        [
            "李林高数辅导讲义复习了中值定理",
            "李林高数 ch3 拉格朗日中值定理整理",
        ],
        [],
    )
    rc, _, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    content = (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").read_text(encoding="utf-8")
    # 章节聚类必须出现
    assert "数学一·高等数学·第3章" in content
    assert "李林高数辅导讲义复习了中值定理" in content
    # 这些 bullet 不应再出现在「逐日产出」未归章节段
    if "逐日产出" in content:
        逐日产出_idx = content.find("逐日产出")
        逐日产出_part = content[逐日产出_idx:]
        assert "李林高数辅导讲义复习了中值定理" not in 逐日产出_part
