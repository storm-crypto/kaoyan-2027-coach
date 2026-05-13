"""test /progress 自动汇总今日错题与迁移总结"""
import json
import textwrap

from helpers import run_script


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

    log_text = (vault_root / "学习日志" / f"{today}.md").read_text(encoding="utf-8")
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
    log_text = (vault_root / "学习日志" / "2026-05-14.md").read_text(encoding="utf-8")
    assert "## 今日错题归档" not in log_text


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
    text_first = (vault_root / "学习日志" / f"{today}.md").read_text(encoding="utf-8")
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

    text_second = (vault_root / "学习日志" / f"{today}.md").read_text(encoding="utf-8")
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

    log_text = (vault_root / "学习日志" / f"{today}.md").read_text(encoding="utf-8")
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
    log_text = (vault_root / "学习日志" / f"{today}.md").read_text(encoding="utf-8")
    assert "[[错题本/数学一/高等数学/无总结卡-真题-qid-ffff00001111|缺迁移总结的题]]" in log_text
    # 卡片下面不能出现 → 学到 行
    card_block = log_text.split("缺迁移总结的题]] — 不会")[1].splitlines()[:3]
    assert not any("→ 学到" in line for line in card_block)
