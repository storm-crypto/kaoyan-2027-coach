"""test /progress 自动汇总今日错题与迁移总结"""
import json
import textwrap

from helpers import log_path, run_script


def _write_card(vault_root, subject, chapter, filename, content):
    card_dir = vault_root / "错题本" / subject / chapter
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / filename
    card.write_text(textwrap.dedent(content), encoding="utf-8")
    return card


def _new_math_card(vault_root, today_iso):
    """卡 A：今日新建的数学一卡片，含「下次怎么做」迁移总结。"""
    return _write_card(
        vault_root,
        "数学一",
        "高等数学",
        f"中值定理-真题-qid-aaaa11112222.md",
        f"""\
        ---
        source: 真题
        question_id: qid-aaaa11112222
        topic: 中值定理三大类的判断
        error_tags: []
        first_wrong_at: {today_iso}
        last_review_at: {today_iso}
        wrong_count: 1
        status: 不会
        next_review: 2026-05-15
        review_interval: 1
        ease_factor: 2.50
        ---

        #subject/math1 #topic/中值定理 #status/不会 #source/真题

        ## 中值定理 — 真题 — qid-aaaa11112222

        ### 题目
        - 设 $f(x)$ 在 $[a,b]$ 上连续...

        ### 考点判断
        - 中值定理类型识别

        ### 第一步怎么想到
        - 看到 $F(x)$ 形式优先构造辅助函数

        ### 规范解法
        - 待补充

        ### 错因定位
        - 待补充

        ### 易错点
        - 待补充

        ### 下次怎么做
        - 见 $F(x)$ 形式先想构造辅助函数，再选 Rolle / Lagrange / Cauchy

        ### 检查你是否真的懂了
        1. 待补充

        ### 历史记录
        - {today_iso} - 不会 - 首次
        """,
    )


def _downgraded_408_card(vault_root, today_iso):
    """卡 B：昨日建卡，今日复习降级为半会，含「记忆钩子」。"""
    return _write_card(
        vault_root,
        "408",
        "数据结构",
        "二叉树遍历-王道-qid-bbbb33334444.md",
        f"""\
        ---
        source: 王道
        question_id: qid-bbbb33334444
        topic: 二叉树遍历的非递归写法
        error_tags: []
        first_wrong_at: 2026-05-10
        last_review_at: {today_iso}
        wrong_count: 2
        status: 半会
        next_review: 2026-05-17
        review_interval: 3
        ease_factor: 2.50
        ---

        #subject/408 #topic/树 #status/半会 #source/王道

        ## 二叉树遍历 — 王道 — qid-bbbb33334444

        ### 题目
        - 给定二叉树，写出后序遍历的非递归算法

        ### 考点定位
        - 二叉树非递归遍历

        ### 题干突破口
        - 待补充

        ### 选项逐个辨析
        - 待补充

        ### 双轨解释
        - 待补充

        ### 干扰项陷阱
        - 待补充

        ### 知识网络串联
        - 待补充

        ### 记忆钩子
        - 后序遍历的非递归写法关键在标记访问过的右子树

        ### 检查你是否真的懂了
        1. 待补充

        ### 历史记录
        - 2026-05-10 - 不会 - 首次
        - {today_iso} - 半会 - 还是不够熟练
        """,
    )


def _passed_math_card(vault_root, today_iso):
    """卡 C：今日复习对了的旧卡，应该被跳过。"""
    return _write_card(
        vault_root,
        "数学一",
        "线性代数",
        "矩阵秩-660题-qid-cccc55556666.md",
        f"""\
        ---
        source: 660题
        question_id: qid-cccc55556666
        topic: 矩阵秩的判定
        error_tags: []
        first_wrong_at: 2026-04-20
        last_review_at: {today_iso}
        wrong_count: 1
        status: 会
        next_review: 2026-07-01
        review_interval: 30
        ease_factor: 2.60
        ---

        #subject/math1 #topic/线代 #status/会 #source/660题

        ## 矩阵秩 — 660题 — qid-cccc55556666

        ### 下次怎么做
        - 不应出现在日志里

        ### 历史记录
        - 2026-04-20 - 不会 - 首次
        - {today_iso} - 会 - 已掌握
        """,
    )


def _inactive_card(vault_root):
    """卡 D：其他日期的卡，今日无活动，应该被跳过。"""
    return _write_card(
        vault_root,
        "政治",
        "马原",
        "矛盾原理-肖1000-qid-dddd77778888.md",
        """\
        ---
        source: 肖1000
        question_id: qid-dddd77778888
        topic: 矛盾普遍性与特殊性
        error_tags: []
        first_wrong_at: 2026-04-01
        last_review_at: 2026-04-15
        wrong_count: 1
        status: 半会
        next_review: 2026-04-20
        review_interval: 5
        ease_factor: 2.50
        ---

        #subject/politics #topic/马原 #status/半会 #source/肖1000

        ## 矛盾原理 — 肖1000 — qid-dddd77778888

        ### 正确思路 / 核心结论
        - 不应出现在日志里

        ### 历史记录
        - 2026-04-01 - 不会 - 首次
        - 2026-04-15 - 半会 - 仍需多练
        """,
    )


def test_log_progress_aggregates_today_wrong_cards(vault_root):
    today = "2026-05-14"
    _new_math_card(vault_root, today)
    _downgraded_408_card(vault_root, today)
    _passed_math_card(vault_root, today)
    _inactive_card(vault_root)

    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", today,
        "--topic", "测试今日错题汇总",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["today_wrong_count"] == 2
    assert data["today_wrong_new"] == 1

    log_text = log_path(vault_root, today).read_text(encoding="utf-8")
    assert "## 今日错题归档" in log_text
    # 卡 A 数学一·高等数学
    assert "### 数学一·高等数学（1 道）" in log_text
    assert "[[错题本/数学一/高等数学/中值定理-真题-qid-aaaa11112222|中值定理三大类的判断]]" in log_text
    assert "— 不会" in log_text
    assert "→ 学到：见 $F(x)$ 形式先想构造辅助函数" in log_text
    # 卡 B 408·数据结构
    assert "### 408·数据结构（1 道）" in log_text
    assert "[[错题本/408/数据结构/二叉树遍历-王道-qid-bbbb33334444|二叉树遍历的非递归写法]]" in log_text
    assert "— 半会" in log_text
    assert "→ 学到：后序遍历的非递归写法关键在标记访问过的右子树" in log_text
    # 卡 C 应被跳过
    assert "矩阵秩" not in log_text
    # 卡 D 应被跳过
    assert "矛盾普遍性" not in log_text
    # 不应出现旧版的相对 markdown 链接（用户在 学习日志/ 下点击会断）
    assert "](错题本/" not in log_text


def test_log_progress_no_today_wrong_omits_section(vault_root):
    """没有今日活跃卡时，日志里不应该有「今日错题归档」标题。"""
    _inactive_card(vault_root)
    rc, _, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", "2026-05-14",
        "--topic", "今天没碰错题",
    ])

    assert rc == 0
    log_text = log_path(vault_root, "2026-05-14").read_text(encoding="utf-8")
    assert "## 今日错题归档" not in log_text


def test_log_progress_prefers_chapter_display_frontmatter(vault_root):
    today = "2026-05-14"
    _write_card(
        vault_root,
        "数学一",
        "高等数学/05第五章不定积分/02第二节不定积分的计算",
        "不定积分-李林-qid-eeee99990000.md",
        f"""\
        ---
        source: 李林
        question_id: qid-eeee99990000
        topic: 不定积分的计算
        chapter_id: math1:gaoshu:05:02
        chapter_path: 高等数学/05第五章不定积分/02第二节不定积分的计算
        chapter_display: 05.02 第二节 不定积分的计算
        error_tags: []
        first_wrong_at: {today}
        last_review_at: {today}
        wrong_count: 1
        status: 不会
        next_review: 2026-05-15
        review_interval: 1
        ease_factor: 2.50
        ---

        #subject/math1 #topic/不定积分 #status/不会 #source/李林

        ## 不定积分 — 李林 — qid-eeee99990000

        ### 下次怎么做
        - 先判断被积函数是否可由某个乘积导数反推

        ### 历史记录
        - {today} - 不会 - 首次
        """,
    )

    rc, _, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", today,
        "--topic", "测试章节展示名",
    ])

    assert rc == 0
    log_text = log_path(vault_root, today).read_text(encoding="utf-8")
    assert "### 数学一·05.02 第二节 不定积分的计算（1 道）" in log_text
    assert "### 数学一·02第二节不定积分的计算" not in log_text


def test_log_progress_groups_legacy_card_with_new_card_by_canonical_chapter(vault_root):
    """历史卡（frontmatter 无 chapter_display）与新卡若同属一个规范章节，应合并到
    同一展示名，不能因为一个读 frontmatter、一个按目录叶子而分裂成两组。"""
    today = "2026-05-14"
    canonical_dir = "高等数学/05第五章不定积分/02第二节不定积分的计算"

    # 新卡：带 chapter_display 等规范字段
    _write_card(
        vault_root,
        "数学一",
        canonical_dir,
        "不定积分-李林-qid-eeee99990000.md",
        f"""\
        ---
        source: 李林
        question_id: qid-eeee99990000
        topic: 不定积分的计算
        chapter_id: math1:gaoshu:05:02
        chapter_path: 高等数学/05第五章不定积分/02第二节不定积分的计算
        chapter_display: 05.02 第二节 不定积分的计算
        error_tags: []
        first_wrong_at: {today}
        last_review_at: {today}
        wrong_count: 1
        status: 不会
        next_review: 2026-05-15
        review_interval: 1
        ease_factor: 2.50
        ---

        #subject/math1 #topic/不定积分 #status/不会 #source/李林

        ## 不定积分 — 李林 — qid-eeee99990000

        ### 下次怎么做
        - 先判断被积函数是否可由某个乘积导数反推

        ### 历史记录
        - {today} - 不会 - 首次
        """,
    )

    # 历史卡：同一规范目录，但缺少 chapter_* 字段（建于本次硬化之前）
    _write_card(
        vault_root,
        "数学一",
        canonical_dir,
        "换元积分-旧卡-qid-dddd88887777.md",
        f"""\
        ---
        source: 旧卡
        question_id: qid-dddd88887777
        topic: 第一类换元
        error_tags: []
        first_wrong_at: {today}
        last_review_at: {today}
        wrong_count: 1
        status: 不会
        next_review: 2026-05-15
        review_interval: 1
        ease_factor: 2.50
        ---

        #subject/math1 #topic/换元积分 #status/不会 #source/旧卡

        ## 换元积分 — 旧卡 — qid-dddd88887777

        ### 下次怎么做
        - 看到复合结构先试第一类换元

        ### 历史记录
        - {today} - 不会 - 首次
        """,
    )

    rc, _, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", today,
        "--topic", "测试新旧卡合并",
    ])

    assert rc == 0
    log_text = log_path(vault_root, today).read_text(encoding="utf-8")
    # 两张卡合并到同一个规范展示名下，计 2 道
    assert "### 数学一·05.02 第二节 不定积分的计算（2 道）" in log_text
    # 不能出现按目录叶子分裂的历史卡表头
    assert "### 数学一·02第二节不定积分的计算" not in log_text


def test_log_progress_today_wrong_section_overwrites_on_rerun(vault_root):
    """同一天多次 /progress 时，今日错题区块应是当前快照而非合并。"""
    today = "2026-05-14"
    # 首次执行：只有卡 A
    _new_math_card(vault_root, today)
    rc, _, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", today,
        "--topic", "第一次",
    ])
    assert rc == 0
    text_first = log_path(vault_root, today).read_text(encoding="utf-8")
    assert "### 数学一·高等数学（1 道）" in text_first
    assert "二叉树遍历" not in text_first

    # 第二次执行：又加了卡 B
    _downgraded_408_card(vault_root, today)
    rc, out2, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", today,
        "--topic", "第二次",
    ])
    assert rc == 0
    data2 = json.loads(out2)
    assert data2["today_wrong_count"] == 2

    text_second = log_path(vault_root, today).read_text(encoding="utf-8")
    # 不应出现两个「今日错题归档」标题
    assert text_second.count("## 今日错题归档") == 1
    assert "### 数学一·高等数学（1 道）" in text_second
    assert "### 408·数据结构（1 道）" in text_second


def test_log_progress_deep_nested_chapter_uses_deepest_directory(vault_root):
    """真实 vault 嵌套很深 (错题本/科目/模块/章/节/卡.md)，章节应取最深一层。"""
    today = "2026-05-14"
    deep_dir = vault_root / "错题本" / "数学一" / "高等数学" / "01第一章函数极限连续" / "04第四节函数的连续性"
    deep_dir.mkdir(parents=True, exist_ok=True)
    card = deep_dir / "幂指型极限先取对数-李林讲义例5-qid-eeee99990000.md"
    card.write_text(textwrap.dedent(f"""\
        ---
        source: 李林讲义
        question_id: qid-eeee99990000
        topic: 幂指型极限先取对数再查零点
        error_tags: []
        first_wrong_at: {today}
        last_review_at: {today}
        wrong_count: 1
        status: 不会
        next_review: 2026-05-15
        review_interval: 1
        ease_factor: 2.50
        ---

        #subject/math1 #topic/连续性 #status/不会

        ## 幂指型极限 — 李林讲义 — qid-eeee99990000

        ### 下次怎么做
        - 底数趋于 $1$ 时先取对数，再查零点

        ### 历史记录
        - {today} - 不会 - 首次
    """), encoding="utf-8")

    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", today,
        "--topic", "深嵌套测试",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["today_wrong_count"] == 1

    log_text = log_path(vault_root, today).read_text(encoding="utf-8")
    # 章节标签必须是最深一层，不是模块「高等数学」也不是章「01第一章...」
    assert "### 数学一·04第四节函数的连续性（1 道）" in log_text
    assert "### 数学一·高等数学" not in log_text
    # wikilink 路径要完整保留嵌套结构
    assert "[[错题本/数学一/高等数学/01第一章函数极限连续/04第四节函数的连续性/幂指型极限先取对数-李林讲义例5-qid-eeee99990000|幂指型极限先取对数再查零点]]" in log_text


def test_log_progress_missing_takeaway_is_silent(vault_root):
    """卡片里「下次怎么做」为空或仅占位时，日志不写 → 学到 行（产品口径：静默）。"""
    today = "2026-05-14"
    card_dir = vault_root / "错题本" / "数学一" / "高等数学"
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / "无总结卡-真题-qid-ffff00001111.md"
    card.write_text(textwrap.dedent(f"""\
        ---
        source: 真题
        question_id: qid-ffff00001111
        topic: 缺迁移总结的题
        error_tags: []
        first_wrong_at: {today}
        last_review_at: {today}
        wrong_count: 1
        status: 不会
        next_review: 2026-05-15
        review_interval: 1
        ease_factor: 2.50
        ---

        #subject/math1

        ## 无总结卡

        ### 下次怎么做
        - 待补充

        ### 历史记录
        - {today} - 不会 - 首次
    """), encoding="utf-8")

    rc, _, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", today,
        "--topic", "静默测试",
    ])

    assert rc == 0
    log_text = log_path(vault_root, today).read_text(encoding="utf-8")
    assert "[[错题本/数学一/高等数学/无总结卡-真题-qid-ffff00001111|缺迁移总结的题]]" in log_text
    # 卡片下面不能出现 → 学到 行
    card_block = log_text.split("缺迁移总结的题]] — 不会")[1].splitlines()[:3]
    assert not any("→ 学到" in line for line in card_block)


def _due_unreviewed_card(vault_root):
    """卡 E：已到期但今日没复习的旧卡，应计入 due_remaining。"""
    return _write_card(
        vault_root,
        "数学一",
        "概率统计",
        "二维正态-660题-qid-eeee11112222.md",
        """\
        ---
        source: 660题
        question_id: qid-eeee11112222
        topic: 二维正态分布的边缘分布
        error_tags: []
        first_wrong_at: 2026-04-01
        last_review_at: 2026-04-10
        wrong_count: 2
        status: 半会
        next_review: 2026-05-10
        review_interval: 4
        ease_factor: 2.50
        ---

        #subject/math1 #topic/概率 #status/半会 #source/660题

        ## 二维正态 — 660题 — qid-eeee11112222

        ### 历史记录
        - 2026-04-01 - 不会 - 首次
        - 2026-04-10 - 半会 - 还差一步
        """,
    )


def test_log_progress_writes_review_effectiveness_section(vault_root):
    """复习效果区块应反映今日复习分布、新增、未触碰的到期卡。"""
    today = "2026-05-14"
    _new_math_card(vault_root, today)             # 新增 +1
    _downgraded_408_card(vault_root, today)       # 复习半会 +1
    _passed_math_card(vault_root, today)          # 复习会 +1
    _due_unreviewed_card(vault_root)              # 到期未复习 +1

    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", today,
        "--topic", "复习效果测试",
    ])

    assert rc == 0
    data = json.loads(out)
    eff = data["review_effectiveness"]
    assert eff["reviewed_today"] == 2
    assert eff["mastered_today"] == 1
    assert eff["partial_today"] == 1
    assert eff["failed_today"] == 0
    assert eff["new_today"] == 1
    assert eff["due_remaining"] == 1
    assert eff["mastery_rate"] == 0.5
    # coverage = 2 / (2+1) ≈ 0.667
    assert eff["coverage_rate"] is not None
    assert abs(eff["coverage_rate"] - 2 / 3) < 1e-6

    log_text = log_path(vault_root, today).read_text(encoding="utf-8")
    assert "## 复习效果" in log_text
    assert "今日复习 **2** 道" in log_text
    assert "今日新增 **1** 道" in log_text
    assert "会 1 / 半会 1 / 不会 0" in log_text
    assert "**掌握转化率**：50.0%" in log_text
    assert "**复习覆盖率**：66.7%（仍有 1 道到期未复习）" in log_text


def test_log_progress_skips_review_effectiveness_when_no_today_activity(vault_root):
    """只有积压卡、没有当天复习/新增时，复习效果区块整段省略——积压不算今日活动。"""
    _inactive_card(vault_root)  # next_review=2026-04-20，已积压；当天没有任何动作

    today = "2026-05-14"
    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", today,
        "--topic", "无活动",
    ])

    assert rc == 0
    data = json.loads(out)
    eff = data["review_effectiveness"]
    assert eff["reviewed_today"] == 0
    assert eff["new_today"] == 0
    assert eff["due_remaining"] >= 1  # 积压仍被统计，只是不再独占该区块
    log_text = log_path(vault_root, today).read_text(encoding="utf-8")
    assert "## 复习效果" not in log_text


def test_log_progress_omits_review_effectiveness_on_empty_vault(vault_root):
    """空 vault：没有任何错题卡时，复习效果区块完全省略。"""
    today = "2026-05-14"
    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", today,
        "--topic", "空 vault",
    ])

    assert rc == 0
    data = json.loads(out)
    eff = data["review_effectiveness"]
    assert eff["reviewed_today"] == 0
    assert eff["new_today"] == 0
    assert eff["due_remaining"] == 0
    log_text = log_path(vault_root, today).read_text(encoding="utf-8")
    assert "## 复习效果" not in log_text


def test_log_progress_historical_rerun_preserves_target_day_review(vault_root):
    """补跑历史日期时，后续日期的复习不应该挤掉当天的复习记录。

    场景：一张卡在 2026-05-14 复习过（半会），又在 2026-05-16 复习过（会）。
    补跑 --date 2026-05-14 时，今日复习应仍然是 2026-05-14 的「半会」。
    """
    card_dir = vault_root / "错题本" / "408" / "操作系统"
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / "进程调度-王道-qid-cdef00001234.md"
    card.write_text(textwrap.dedent("""\
        ---
        source: 王道
        question_id: qid-cdef00001234
        topic: 进程调度算法对比
        error_tags: []
        first_wrong_at: 2026-05-10
        last_review_at: 2026-05-16
        wrong_count: 1
        status: 会
        next_review: 2026-05-20
        review_interval: 3
        ease_factor: 2.60
        ---

        #subject/408 #topic/OS #status/会 #source/王道

        ## 进程调度 — 王道 — qid-cdef00001234

        ### 历史记录
        - 2026-05-10 - 不会 - 首次
        - 2026-05-14 - 半会 - 思路对了步骤乱
        - 2026-05-16 - 会 - 这次稳了
        """), encoding="utf-8")

    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", "2026-05-14",
        "--topic", "历史重跑",
    ])

    assert rc == 0
    data = json.loads(out)
    eff = data["review_effectiveness"]
    assert eff["reviewed_today"] == 1
    assert eff["partial_today"] == 1
    assert eff["mastered_today"] == 0
    log_text = log_path(vault_root, "2026-05-14").read_text(encoding="utf-8")
    assert "## 复习效果" in log_text
    assert "今日复习 **1** 道" in log_text
    assert "会 0 / 半会 1 / 不会 0" in log_text


def test_log_progress_historical_due_remaining_uses_snapshot(vault_root):
    """到期未复习应按 log_day 当天快照算，不被后续复习把 next_review 推走。

    场景：一张卡 first_wrong_at=2026-04-01，初始 next_review=2026-04-02；
    后续在 2026-05-16 复习一次（会，interval 推到 2 天）。
    补跑 --date 2026-05-14 + 新增一张今日卡（让区块不被 has_activity 省略）：
    旧卡当天到期未复习应被计入 due_remaining=1，不论 frontmatter 的 next_review。
    """
    # 旧卡：今日尚未复习，但当天前 next_review 已到期
    old_card_dir = vault_root / "错题本" / "数学一" / "线性代数"
    old_card_dir.mkdir(parents=True, exist_ok=True)
    old_card = old_card_dir / "矩阵相似-660题-qid-abcd56781234.md"
    old_card.write_text(textwrap.dedent("""\
        ---
        source: 660题
        question_id: qid-abcd56781234
        topic: 矩阵相似与对角化判定
        error_tags: []
        first_wrong_at: 2026-04-01
        last_review_at: 2026-05-16
        wrong_count: 1
        status: 会
        next_review: 2026-05-18
        review_interval: 2
        ease_factor: 2.60
        ---

        #subject/math1 #topic/线代 #status/会 #source/660题

        ## 矩阵相似 — 660题 — qid-abcd56781234

        ### 历史记录
        - 2026-04-01 - 不会 - 首次
        - 2026-05-16 - 会 - 已掌握
        """), encoding="utf-8")

    # 今日新增卡：让区块通过 has_activity 检查
    new_card_dir = vault_root / "错题本" / "数学一" / "高等数学"
    new_card_dir.mkdir(parents=True, exist_ok=True)
    new_card = new_card_dir / "今日新题-真题-qid-1234aaaabbbb.md"
    new_card.write_text(textwrap.dedent("""\
        ---
        source: 真题
        question_id: qid-1234aaaabbbb
        topic: 今日新题占位
        error_tags: []
        first_wrong_at: 2026-05-14
        last_review_at: 2026-05-14
        wrong_count: 1
        status: 不会
        next_review: 2026-05-15
        review_interval: 1
        ease_factor: 2.50
        ---

        #subject/math1

        ## 今日新题

        ### 历史记录
        - 2026-05-14 - 不会 - 首次
        """), encoding="utf-8")

    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", "2026-05-14",
        "--topic", "历史 due 快照",
    ])

    assert rc == 0
    data = json.loads(out)
    eff = data["review_effectiveness"]
    # 旧卡的 next_review 在重放下应是 2026-04-02（建卡时 interval=1）
    # 远早于 2026-05-14，所以当天到期未复习 → due_remaining = 1
    # 即便 frontmatter 当前 next_review=2026-05-18，也不影响快照判定
    assert eff["due_remaining"] == 1
    assert eff["new_today"] == 1
