"""共享测试 fixtures。"""
import sys
import textwrap
from pathlib import Path

# 让 test 文件能 import helpers
sys.path.insert(0, str(Path(__file__).parent))

import pytest


@pytest.fixture
def vault_root(tmp_path):
    """创建一个最小化的 vault 目录结构。"""
    dirs = [
        "错题本/数学一/高等数学",
        "错题本/408/数据结构",
        "知识地图",
        "学习日志",
    ]
    for d in dirs:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def sample_card(vault_root):
    """创建一个带完整 frontmatter 的示例错题卡。"""
    card_dir = vault_root / "错题本" / "数学一" / "高等数学"
    card = card_dir / "二重积分极坐标-900题-qid-f728c5b18974.md"
    card.write_text(textwrap.dedent("""\
        ---
        source: 900题
        question_id: qid-f728c5b18974
        topic: 二重积分极坐标变换
        error_tags: [极坐标, 积分上下限]
        first_wrong_at: 2026-03-01
        last_review_at: 2026-03-15
        wrong_count: 3
        status: 半会
        next_review: 2026-03-20
        review_interval: 4
        ease_factor: 2.50
        ---

        #subject/math1 #topic/多元积分 #status/半会 #source/900题

        ## 二重积分极坐标 — 900题 — qid-f728c5b18974

        ### 错误原因
        - 极坐标变换时上下限搞反

        ### 正确思路 / 核心结论
        - 先画积分区域，再确定角度范围

        ### 易错点 / 变式提醒
        - 注意 r 的范围

        ### 历史记录
        - 2026-03-01 - 不会 - 首次
        - 2026-03-10 - 半会 - 思路对了但计算错
        - 2026-03-15 - 半会 - 还是不够熟练
    """), encoding="utf-8")
    return card


@pytest.fixture
def sample_card_no_qid(vault_root):
    """创建一个没有 question_id 的旧卡。"""
    card_dir = vault_root / "错题本" / "数学一" / "高等数学"
    card = card_dir / "泰勒展开-660题.md"
    card.write_text(textwrap.dedent("""\
        ---
        source: 660题
        topic: 泰勒展开应用
        error_tags: []
        first_wrong_at: 2026-02-20
        last_review_at: 2026-02-20
        wrong_count: 1
        status: 不会
        next_review: 2026-02-21
        review_interval: 1
        ---

        #subject/math1 #topic/泰勒展开 #status/不会 #source/660题

        ## 泰勒展开 — 660题

        ### 错误原因
        - 展开阶数不够

        ### 历史记录
        - 2026-02-20 - 不会 - 首次
    """), encoding="utf-8")
    return card


@pytest.fixture
def knowledge_map(vault_root):
    """创建一个简化版知识地图。"""
    km_dir = vault_root / "知识地图"
    content = textwrap.dedent("""\
        # 数学一 知识地图

        ## 高等数学（约 56%）

        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **01 函数、极限与连续** |  |  |  |
        |  01.1 函数的概念与性质 |  |  |  |
        |  01.2 极限的定义与计算 |  |  |  |
        | **05 多元函数微积分** |  |  |  |
        |  05.1 偏导数与全微分 |  |  |  |
        |  05.5 二重积分 |  |  |  |
        |  05.6 三重积分 |  |  |  |
    """)
    (km_dir / "数学一.md").write_text(content, encoding="utf-8")
    return km_dir
