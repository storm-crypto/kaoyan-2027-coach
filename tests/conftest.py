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
        "复盘报告",
        "周计划",
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


@pytest.fixture
def sample_archive(vault_root):
    """创建一个带目标分数和聚焦问题的学习者档案。"""
    archive = vault_root / "我的学习者档案.md"
    archive.write_text(textwrap.dedent("""\
        # 我的学习者档案

        ## 基本信息
        - **目标院校/专业**：计算机科学与技术
        - **当前目标总分**：360
        - **考试日期**：2026-12-20
        - **每日可投入时长**：6
        - **最近更新日期**：2026-03-20
        - **当前阶段关键词**：408重构期 / 数学提速期

        ## 各科当前状态
        | 科目 | 当前水平 | 目标 | 差距 | 当前判断 |
        |------|----------|------|------|----------|
        | 政治 | 55 | 70 | 15 | 选择题基础薄 |
        | 数学一 | 105 | 125 | 20 | 计算和方法都要提速 |
        | 英语一 | 72 | 80 | 8 | 阅读速度偏慢 |
        | 408 | 92 | 100 | 8 | OS 和计网容易失分 |

        ## 模考成绩追踪
        | 日期 | 政治 | 数学一 | 英语一 | 408 | 总分 | 备注 |
        |------|------|--------|--------|-----|------|------|
        | 2026-03-01 | 60 | 110 | 76 | 92 | 338 | 阶段基准 |

        ## 最近聚焦问题（只保留 3-5 条）
        - 数学二重积分和极坐标切换总卡
        - 408 操作系统调度和死锁题反复错
        - 英语阅读定位速度偏慢

        ## 短板雷达
        | 短板 | 科目 | 严重度 | 证据 | 当前状态 | 下一步 |
        |------|------|--------|------|----------|--------|
        | OS 调度 | 408 | 高 | 最近三次都出错 | 待攻坚 | 周内补专题 |

        ## 高频错误模式统计
        | 错误模式 | 科目 | 出现频率 | 最近一次出现 | 备注 |
        |----------|------|----------|--------------|------|
        | 积分上下限混乱 | 数学一 | 3 次 | 2026-03-18 | 极坐标切换时最明显 |

        ## 下一步建议（只保留 3 条）
        1. 数学优先提速
        2. 408 专题化复盘
        3. 英语保持阅读节奏
    """), encoding="utf-8")
    return archive
