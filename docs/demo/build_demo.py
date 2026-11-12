#!/usr/bin/env python3
"""构建 README 截图用的虚构学习库；只写显式指定的空目录。

用法：python3 docs/demo/build_demo.py /tmp/kaoyan-coach-demo
日期固定为 2026-11-11，不读取个人学习库或 KAOYAN_OBSIDIAN_ROOT。
截图展示生产工作台，全部目标、题卡、成绩与学习记录都是虚构示例。
"""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys
import textwrap

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
DAY = "2026-11-11"
sys.path.insert(0, str(SCRIPTS))

from card_progress import upsert_card_progress
from log_layout import log_path_for
from textbook_progress import week_plan_path
from wrong_card_path_map import iter_408_knowledge_map_rows


def write(root, relative, content):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def run(script, *args):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *map(str, args)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def make_cards(root):
    # 日期和作答轨迹是固定的演示数据，不代表真实学习结果。
    cards = [
        ("a00000000001", "数学一/高等数学/06 第六章 定积分及其应用/01 第一节 定积分的计算",
         "定积分区间对称代换", "半会", "2026-11-11", ["不会", "半会", "半会"],
         r"设 $f(x)=\frac{x}{1+\sin x}$，说明计算 $\int_0^\pi f(x)\,\mathrm dx$ 时如何利用区间对称性。",
         "只替换分子，忘记同时替换分母。"),
        ("a00000000002", "数学一/高等数学/06 第六章 定积分及其应用/01 第一节 定积分的计算",
         "对称区间上的奇偶拆分", "会", "2026-11-17", ["不会", "会", "会", "会"],
         r"计算 $\int_{-1}^{1}\frac{x^3+1}{1+x^2}\,\mathrm dx$。",
         "先拆成奇函数部分与偶函数部分。"),
        ("a00000000003", "数学一/高等数学/10 第十章 二重积分/02 第二节 二重积分的计算",
         "圆域二重积分的极坐标", "不会", "2026-11-10", ["不会", "半会", "不会"],
         r"区域 $D$ 为 $x^2+y^2\leq x$，写出 $\iint_D 1\,\mathrm dx\mathrm dy$ 的极坐标积分式。",
         "径向边界与角度范围没有一起检查。"),
        ("a00000000004", "数学一/高等数学/10 第十章 二重积分/02 第二节 二重积分的计算",
         "扇形区域的积分限", "会", "2026-11-11", ["不会", "半会", "会"],
         r"区域 $D$ 满足 $1\leq x^2+y^2\leq4$ 且 $0\leq y\leq x$，写出极坐标积分限。",
         "把直线条件转换为角度条件后再定积分限。"),
        ("a00000000005", "408/操作系统/08 第八章 互斥和同步/02 死锁",
         "银行家算法的安全序列", "不会", "2026-11-09", ["不会", "不会", "不会"],
         "给定 Available、Allocation 与 Need，安全性检查中进程能否完成应比较哪两个向量？进程完成后 Work 如何更新？",
         "误把 Max 与可用资源比较，未扣除已分配量。"),
        ("a00000000006", "408/操作系统/08 第八章 互斥和同步/02 死锁",
         "不安全状态与死锁", "半会", "2026-11-11", ["不会", "半会", "半会"],
         "判断：系统进入不安全状态就已经发生死锁。请说明不安全与死锁的关系。",
         "把无法保证顺利完成等同于已经无法推进。"),
    ]
    for qid, chapter, topic, status, due, states, question, reason in cards:
        interval = (7 if states[-3:] == ["会"] * 3 else 3) if status == "会" else 1
        last_review = date.fromisoformat(due) - timedelta(days=interval)
        dates = [(last_review - timedelta(days=2 * offset)).isoformat()
                 for offset in reversed(range(len(states)))]
        history = "\n".join(f"- {day} - {state} - 虚构演示作答" for day, state in zip(dates, states))
        body = f"""
## {topic} — 虚构示例 — qid-{qid}

### 题目
{question}

### 错误原因
- {reason}

### 历史记录
{history}
"""
        frontmatter = f"""---
source: 虚构演示题
question_id: qid-{qid}
topic: {topic}
error_tags: []
first_wrong_at: {dates[0]}
last_review_at: {dates[-1]}
wrong_count: {states.count('不会')}
status: {status}
next_review: {due}
review_interval: {interval}
ease_factor: 2.50
---
"""
        write(root, f"错题本/{chapter}/{topic}-qid-{qid}.md", frontmatter + upsert_card_progress(body))
    clusters = [
        {"id": "m06-01", "name": "区间对称代换", "ch": "ch6 定积分及其应用", "family": "对称性", "min": 25,
         "qids": ["a00000000001", "a00000000002"], "also": [],
         "skill": "看到什么：\n积分区间为 $[a,b]$，且 $f(x)$ 与 $f(a+b-x)$ 的和或差更简单。\n\n怎么做：\n1. 令 $x=a+b-t$，同时替换被积函数、微分与上下限。\n2. 将新旧积分相加或相减，利用对称关系化简。\n3. 计算简化后的积分，再还原原积分。\n\n适用边界：\n- 先确认积分存在。\n- 必须检查整个被积函数的变化，不能只替换分子。"},
        {"id": "m10-01", "name": "极坐标定积分限", "ch": "ch10 二重积分", "family": "区域与坐标变换", "min": 30,
         "qids": ["a00000000003", "a00000000004"], "also": [],
         "skill": "看到什么：\n积分区域含圆、扇形或 $x^2+y^2$。\n\n怎么做：\n1. 画出区域，先确定从原点出发的射线扫过的角度范围。\n2. 固定角度，沿射线由近到远确定径向上下限。\n3. 将面积元换成 $r\\,\\mathrm dr\\mathrm d\\theta$，检查是否遗漏因子 $r$。\n\n适用边界：\n- 同一射线穿过多段区域时需要拆分。\n- 圆心不在原点时，径向边界可能随角度改变。"},
        {"id": "os08-01", "name": "安全性检查", "ch": "第八章 互斥和同步 · 死锁", "family": "资源状态推演", "min": 25,
         "qids": ["a00000000005", "a00000000006"], "also": [],
         "skill": "看到什么：\n给出可用资源、已分配资源和最大需求，要求判断状态是否安全。\n\n怎么做：\n1. 用最大需求减去已分配量，得到每个进程的尚需资源。\n2. 从未完成进程中，找尚需资源不超过当前可用资源的进程。\n3. 模拟该进程完成并归还已分配资源，继续检查其余进程。\n\n适用边界：\n- 找不到安全序列表示不安全，不能直接断言已经死锁。\n- 多类资源需逐项比较，不能只比较总数。"},
    ]
    write(root, "错题本/_元技能索引.json", json.dumps({"clusters": clusters}, ensure_ascii=False, indent=2))


def seed(root):
    (root / ".obsidian").mkdir()
    write(root, "演示数据说明.md", "# 虚构演示库\n\n仅用于 README 截图。所有目标、日期、题卡、成绩和历史记录均为虚构；不含个人数据。")
    write(root, "我的学习者档案.md", """
        # 我的学习者档案（虚构演示）

        ## 基本信息
        - **目标院校/专业**：示例院校 · 计算机（虚构）
        - **当前目标总分**：380
        - **考试日期**：2026-12-20
        - **每日可投入时长**：6
        - **最近更新日期**：2026-11-11
        - **当前阶段关键词**：专题巩固 / 限时训练

        ## 各科当前状态
        | 科目 | 当前水平 | 目标 | 差距 | 当前判断 |
        |------|----------|------|------|----------|
        | 政治 | 65 | 70 | 5 | 多选题继续巩固 |
        | 数学一 | 118 | 125 | 7 | 积分限与计算速度 |
        | 英语一 | 78 | 80 | 2 | 写作限时输出 |
        | 408 | 105 | 105 | 0 | 死锁专题仍需验收 |

        ## 模考成绩追踪
        | 日期 | 政治 | 数学一 | 英语一 | 408 | 总分 | 备注 |
        |------|------|--------|--------|-----|------|------|
        | 2026-10-25 | 60 | 108 | 74 | 96 | 338 | 虚构阶段训练 |
        | 2026-11-01 | 63 | 114 | 76 | 101 | 354 | 虚构阶段训练 |
        | 2026-11-08 | 65 | 118 | 78 | 105 | 366 | 虚构阶段训练 |

        ## 最近聚焦问题
        - 数学一：极坐标积分限与对称代换
        - 408：安全性检查与死锁概念辨析

        ## 短板雷达
        | 短板 | 科目 | 严重度 | 证据 | 当前状态 | 下一步 |
        |------|------|--------|------|----------|--------|
        | 安全性检查 | 408 | 高 | 演示题连续失误 | 待攻坚 | 无提示重做并解释边界 |

        ## 高频错误模式统计
        | 错误模式 | 科目 | 出现频率 | 最近一次出现 | 备注 |
        |----------|------|----------|--------------|------|
        | 只看公式不画区域 | 数学一 | 3 次 | 2026-11-10 | 虚构示例 |

        ## 下一步建议
        1. 先做安全性检查，再完成数学积分专题。
        2. 每次复习先独立作答，再核对解析。
    """)
    write(root, "周计划/_今日计划.md", f"""
        # 今日计划：{DAY}

        ## 任务清单
        - [x] [英语一] 阅读定位与长难句复盘（0.5 小时）
          - 已完成 2 篇阅读，核对证据句。
        - [ ] [408] 死锁专题：独立走完安全性检查（1 小时）
          - 先做两道旧题，再口述不安全与死锁的区别。
          - 验收：无提示写出资源变化，并说明结论依据。
        - [ ] [数学一] 极坐标积分限与对称代换（1.5 小时）
          - 先画区域，再写积分式；复查面积元。
        - [ ] [英语一] 小作文限时输出与修改（0.75 小时）
          - 独立完成一篇，再修改衔接与任务要点。
        - [ ] [政治] 多选错题复盘与概念辨析（0.75 小时）
          - 解释错项，区分适用条件。

        ## 收尾提醒
        用 /progress 补充实际时长与明日安排。
    """)
    write(root, week_plan_path(root, date.fromisoformat(DAY)).relative_to(root), """
        # 本周计划（虚构演示）

        ## 科目分配
        | 科目 | 时长 | 比例 | 本周主线 |
        |------|------|------|----------|
        | 数学一 | 14h | 40% | 打通积分限与对称代换 |
        | 408 | 11h | 31% | 死锁专题无提示验收 |
        | 英语一 | 6h | 17% | 保持阅读，练习限时写作 |
        | 政治 | 4h | 12% | 复盘多选错项与概念边界 |

        ## 本周教材进度目标
        | 教材 | 起点 | 终点 | 当前 | 备注 |
        |------|------|------|------|------|
        | 高数讲义 · 积分专题 | p120 | p156 | p138 | 页码为虚构演示 |
        | 408 讲义 · 互斥和同步 | p80 | p110 | p96 | 配合旧题验收 |
    """)
    make_cards(root)
    # 408 节名直接取规范大纲，不在演示数据里维护另一份目录。
    os_chapter = [(chapter, topic) for module, chapter, topic in iter_408_knowledge_map_rows()
                  if module == "操作系统" and chapter.startswith("08 ")]
    os_status = {"08.01": "会", "08.02": "不会", "08.03": "半会", "08.04": ""}
    os_rows = [(f"**{os_chapter[0][0]}**", "", "")]
    os_rows.extend((topic, os_status[topic.split()[0]],
                    "1. [2026-11-08] 尚需资源比较出错 (qid-a00000000005)" if topic.startswith("08.02 ") else "")
                   for _, topic in os_chapter)
    maps = {
        "数学一": ("高等数学", [
            ("**06 第六章 定积分及其应用**", "", ""),
            ("06.01 第一节 定积分的计算", "半会", "1. [2026-11-10] 代换时遗漏分母 (qid-a00000000001)"),
            ("06.02 第二节 积分变限函数的求导问题", "会", ""),
            ("**10 第十章 二重积分**", "", ""),
            ("10.02 第二节 二重积分的计算", "不会", "1. [2026-11-09] 角度范围不清 (qid-a00000000003)"),
            ("10.04 第四节 二重积分的应用", "", "")]),
        "408": ("操作系统", os_rows),
        "英语一": ("阅读与写作", [("**01 阅读理解**", "", ""), ("01.1 细节定位", "会", ""), ("01.2 推断题", "半会", ""), ("**02 写作**", "", ""), ("02.1 应用文任务要点", "", "")]),
        "政治": ("马克思主义基本原理", [("**01 唯物辩证法**", "", ""), ("01.1 矛盾普遍性与特殊性", "半会", ""), ("01.2 否定之否定", "", "")]),
    }
    for subject, (module, rows) in maps.items():
        content = f"# {subject} 知识地图（虚构演示）\n\n## {module}\n\n| 考点 | 掌握度 | 信心 | 备注 |\n|------|--------|------|------|\n"
        content += "\n".join(f"| {topic} | {status} | | {note} |" for topic, status, note in rows)
        write(root, f"知识地图/{subject}.md", content)
    for day, hours in [("2026-11-09", 5.5), ("2026-11-10", 6), (DAY, 0.5)]:
        write(root, log_path_for(root, date.fromisoformat(day)).relative_to(root), f"""
            # Session: {day}

            ## 今日概览
            - **主题**: 数学积分专题与 408 互斥和同步（虚构）
            - **时长**: {hours}
            - **模式**: 专题巩固

            ## 学到了什么
            - 学习::极坐标积分先画区域，再定射线范围（数学一·高数·ch10）
            - 学习::不安全状态不等于已经发生死锁（408·OS·ch8）

            ## 卡壳与挣扎
            - 卡点::安全性检查需要逐项比较资源向量（408·OS·ch8）
        """)
    for subject, scores in [("数学一", [108, 114, 118]), ("408", [96, 101, 105])]:
        for number, (day, score) in enumerate(zip(["2026-10-25", "2026-11-01", "2026-11-08"], scores), 1):
            run("record_paper_score.py", root, subject, "--paper", f"虚构演示卷 {number}",
                "--paper-type", "模拟", "--total", score, "--date", day,
                "--issues", "积分限与速度" if subject == "数学一" else "死锁与安全性检查", "--note", "仅供截图，不是真实成绩")
    # 成绩记录会更新档案日期；固定回演示当天，保证每次构建结果一致。
    archive = root / "我的学习者档案.md"
    text = archive.read_text(encoding="utf-8")
    import re
    text = re.sub(r"(\*\*最近更新日期\*\*[：:]\s*)\d{4}-\d{2}-\d{2}", rf"\g<1>{DAY}", text)
    archive.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="新建或为空的演示库目录（必填）")
    args = parser.parse_args()
    root = args.output.expanduser().absolute()
    if root.is_symlink() or (root.exists() and (not root.is_dir() or any(root.iterdir()))):
        parser.error("输出路径必须是新目录或空目录；不会覆盖已有学习库。")
    root.mkdir(parents=True, exist_ok=True)
    seed(root)
    payload = run("build_dashboard.py", root, "--today", DAY)
    wb = payload["workbench"]
    assert wb["plan"]["current"] and wb["plan"]["done"] == 1
    assert len(wb["plan"]["pending"]) == 4
    assert len(wb["metaskills"]["clusters"]) == 3
    assert wb["metaskills"]["total_cards"] == 6
    assert sum(group["count"] for group in wb["reviews"]) == 5
    assert not wb["metaskills"]["warnings"]
    print(json.dumps({"demo_date": DAY, "fictional": True, "path": payload["path"],
                      "statistics_path": payload["statistics_path"], "cards": 6,
                      "due_cards": 5, "clusters": 3, "pending_tasks": 4}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
