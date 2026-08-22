"""test create_wrong_card.py"""
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from archive_ops import extract_heading_block
from create_wrong_card import sanitize_tag_value
from frontmatter import parse_frontmatter
from helpers import run_script


def required_detail_args(subject):
    if subject == "数学一":
        return [
            "--point-judgment", "题型判断清楚，知道先看定理条件。",
            "--first-step", "先核对题目给出的连续与可导条件。",
            "--formal-solution", "按定理条件逐项验证，再写出结论。",
            "--mistake-analysis", "容易把定理条件和结论混在一起。",
            "--pitfall", "别跳过条件核对这一步。",
            "--next-time", "下次先判定题型，再决定调用哪个定理。",
            "--check-question", "如果缺少某个条件，这条解法还成立吗？",
        ]
    if subject == "408":
        return [
            "--point-location", "题目先看考点归属和核心判断轴。",
            "--breakthrough", "抓住题干里的限定条件，再判断选项。",
            "--option-analysis", "逐项解释每个选项为什么对或错。",
            "--dual-track", "先给正式定义，再给直观理解。",
            "--trap", "最容易错在把局部结论误当全局结论。",
            "--knowledge-link", "把这个点挂回同章节的知识网络。",
            "--memory-hook", "先抓判断轴，再排干扰项。",
            "--check-question", "删掉一个条件后答案会不会变？",
        ]
    return [
        "--wrong-reason", "核心概念没分清。",
        "--solution", "回到题干条件，按逻辑链重新判断。",
        "--pitfall", "注意不要把相近概念混用。",
    ]


def test_create_wrong_card_preserves_all_explicit_options(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "408",
        "--chapter", "操作系统",
        "--topic", "进程调度",
        "--source", "王道",
        "--question-id", "qid-aabbccddeeff",
        "--question", "以下关于进程调度的说法，正确的是：",
        "--option", "A. FCFS 总能让平均周转时间最小",
        "--option", "B. 时间片轮转适合交互式系统",
        "--option", "C. SJF 一定不会饥饿",
        "--option", "D. 高响应比优先综合考虑等待时间和服务时间",
        *required_detail_args("408"),
        "--today", "2026-03-23",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["option_count"] == 4
    assert data["options_source"] == "explicit"
    card_path = Path(data["path"])
    content = card_path.read_text(encoding="utf-8")
    question_block = extract_heading_block(content, "题目", level=3)
    assert "### 选项（如有）" not in content
    assert "A. FCFS 总能让平均周转时间最小" in question_block
    assert "B. 时间片轮转适合交互式系统" in question_block
    assert "C. SJF 一定不会饥饿" in question_block
    assert "D. 高响应比优先综合考虑等待时间和服务时间" in question_block


def test_create_wrong_card_keeps_inline_options_inside_question_block(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "408",
        "--chapter", "数据结构",
        "--topic", "二叉树遍历",
        "--source", "王道",
        "--question-id", "qid-112233445566",
        "--question",
        "下列关于二叉树遍历的说法，正确的是：\nA. 先序遍历一定有序\nB. 中序遍历二叉搜索树可得有序序列\nC. 后序遍历总能唯一还原二叉树\nD. 层序遍历不需要队列",
        *required_detail_args("408"),
        "--today", "2026-03-23",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["option_count"] == 0
    assert data["options_source"] == "none"
    card_path = Path(data["path"])
    content = card_path.read_text(encoding="utf-8")
    question_block = extract_heading_block(content, "题目", level=3)
    assert "下列关于二叉树遍历的说法，正确的是：" in question_block
    assert "A. 先序遍历一定有序" in question_block
    assert "D. 层序遍历不需要队列" in question_block
    assert "### 选项（如有）" not in content


def test_create_wrong_card_uses_env_var_root_when_cli_root_omitted(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        "408",
        "--chapter", "计算机组成原理",
        "--topic", "总线仲裁",
        "--source", "王道",
        "--question-id", "qid-5566778899aa",
        "--question", "总线仲裁的核心目标是什么？",
        *required_detail_args("408"),
        "--today", "2026-03-23",
    ], env_extra={"KAOYAN_OBSIDIAN_ROOT": str(vault_root)})

    assert rc == 0
    data = json.loads(out)
    assert Path(data["path"]).is_relative_to(vault_root)


def test_create_wrong_card_uses_multilevel_path_mapping_for_math1(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "数列极限",
        "--topic", "递推数列不动点",
        "--source", "李林",
        "--question-id", "qid-001122334455",
        "--question", "设递推数列满足给定关系，求极限。",
        *required_detail_args("数学一"),
        "--today", "2026-03-23",
    ])

    assert rc == 0
    data = json.loads(out)
    card_path = Path(data["path"])
    assert card_path.is_relative_to(vault_root)
    assert data["chapter"] == "01.03 第三节 数列极限"
    assert data["chapter_id"] == "math1:gaoshu:01:03"
    assert data["chapter_path"] == "高等数学/01第一章函数、极限、连续/03第三节数列极限"
    assert card_path.parent == (
        vault_root
        / "错题本"
        / "数学一"
        / "高等数学"
        / "01第一章函数、极限、连续"
        / "03第三节数列极限"
    )
    fm, _, _ = parse_frontmatter(card_path.read_text(encoding="utf-8"))
    assert fm["chapter_id"] == "math1:gaoshu:01:03"
    assert fm["chapter_path"] == "高等数学/01第一章函数、极限、连续/03第三节数列极限"
    assert fm["chapter_display"] == "01.03 第三节 数列极限"


def test_create_wrong_card_rejects_unmapped_math1_chapter(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "未配置章节",
        "--topic", "未配置路径",
        "--source", "李林",
        "--question-id", "qid-112211221122",
        "--question", "设函数满足条件，求结论。",
        *required_detail_args("数学一"),
        "--today", "2026-03-23",
    ])

    assert rc == 1
    data = json.loads(out)
    assert "无法识别 数学一 章节" in data["message"]
    assert "拒绝按原文创建目录" in data["message"]
    assert not (vault_root / "错题本" / "数学一" / "未配置章节").exists()


def test_create_wrong_card_accepts_math1_section_alias_without_creating_shallow_dir(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "05.02第二节不定积分的计算",
        "--topic", "不定积分的计算",
        "--source", "李林",
        "--question-id", "qid-121212121212",
        "--question", "求不定积分。",
        *required_detail_args("数学一"),
        "--today", "2026-03-23",
    ])

    assert rc == 0
    data = json.loads(out)
    card_path = Path(data["path"])
    assert data["chapter"] == "05.02 第二节 不定积分的计算"
    assert data["chapter_id"] == "math1:gaoshu:05:02"
    assert card_path.parent == (
        vault_root
        / "错题本"
        / "数学一"
        / "高等数学"
        / "05第五章不定积分"
        / "02第二节不定积分的计算"
    )
    assert not (vault_root / "错题本" / "数学一" / "05.02第二节不定积分的计算").exists()


def test_create_wrong_card_reports_unknown_subject_instead_of_treating_it_as_root(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        "数学二",
        "--chapter", "二重积分",
        "--topic", "导数定义",
        "--source", "660题",
        "--question-id", "qid-99aabbccdd11",
        "--question", "设函数在一点可导，说明其连续。",
        "--today", "2026-03-23",
    ], env_extra={"KAOYAN_OBSIDIAN_ROOT": str(vault_root)})

    assert rc == 1
    data = json.loads(out)
    assert "未知科目" in data["message"]
    assert "数学二" in data["message"]


def test_create_wrong_card_keeps_option_like_stem_and_following_lines_together(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "408",
        "--chapter", "操作系统",
        "--topic", "进程调度判断轴",
        "--source", "王道",
        "--question-id", "qid-334455667788",
        "--question",
        "A.教授提出的调度观点最符合下列哪一项？\nA. FCFS 总能让平均周转时间最小\nB. 时间片轮转适合交互式系统\nC. SJF 一定不会饥饿\nD. 高响应比优先综合考虑等待时间和服务时间",
        *required_detail_args("408"),
        "--today", "2026-03-23",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["option_count"] == 0
    assert data["options_source"] == "none"
    content = Path(data["path"]).read_text(encoding="utf-8")
    question_block = extract_heading_block(content, "题目", level=3)
    assert "A.教授提出的调度观点最符合下列哪一项？" in question_block
    assert "A. FCFS 总能让平均周转时间最小" in question_block
    assert "D. 高响应比优先综合考虑等待时间和服务时间" in question_block
    assert "### 选项（如有）" not in content


def test_create_wrong_card_omits_legacy_option_section_for_non_choice_question(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "二重积分",
        "--topic", "二重积分",
        "--source", "900题",
        "--question-id", "qid-f728c5b18974",
        "--question", "设 D 为单位圆与第一象限的交集，求二重积分。",
        *required_detail_args("数学一"),
        "--today", "2026-03-23",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["option_count"] == 0
    assert data["options_source"] == "none"
    card_path = Path(data["path"])
    content = card_path.read_text(encoding="utf-8")
    assert "### 选项（如有）" not in content
    assert "### 考点判断" in content
    assert "### 第一步怎么想到" in content
    assert "### 规范解法" in content
    assert "### 错因定位" in content
    assert "### 下次怎么做" in content


def test_create_wrong_card_renders_math_detailed_sections(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "函数极限",
        "--topic", "中值定理",
        "--source", "660题",
        "--question-id", "qid-a1b2c3d4e5f6",
        "--question", "设 f 在区间上连续可导，证明存在一点满足拉格朗日中值定理结论。",
        "--point-judgment", "证明题；高数中值定理；中频；突破口是先核对定理条件。",
        "--first-step", "看到连续可导，就先想到拉格朗日中值定理。",
        "--formal-solution", "先验证闭区间连续、开区间可导，再直接套定理。",
        "--mistake-analysis", "你把罗尔定理和拉格朗日中值定理的结论混了。",
        "--pitfall", "别漏掉闭区间连续和开区间可导两个条件。",
        "--next-time", "以后先核对条件，再决定套哪个中值定理。",
        "--check-question", "如果缺少可导条件，原方法还成立吗？",
        "--check-question", "这题第一步为什么先查定理条件？",
        "--today", "2026-03-23",
    ])

    assert rc == 0
    content = Path(json.loads(out)["path"]).read_text(encoding="utf-8")
    assert "### 考点判断" in content
    assert "证明题；高数中值定理；中频；突破口是先核对定理条件。" in content
    assert "### 第一步怎么想到" in content
    assert "看到连续可导，就先想到拉格朗日中值定理。" in content
    assert "### 规范解法" in content
    assert "### 错因定位" in content
    assert "### 易错点" in content
    assert "### 下次怎么做" in content
    assert "### 检查你是否真的懂了" in content
    assert "1. 如果缺少可导条件，原方法还成立吗？" in content
    assert "2. 这题第一步为什么先查定理条件？" in content


def test_create_wrong_card_respects_initial_status_without_extra_history(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "函数极限",
        "--topic", "复合极限",
        "--source", "李林",
        "--question-id", "qid-123456abcdef",
        "--question", "求极限并说明理由。",
        "--point-judgment", "复合极限题，先看外层结构。",
        "--first-step", "先识别是否能用中值定理降成内层差。",
        "--formal-solution", "按中值定理展开后再做等价替换。",
        "--mistake-analysis", "答案能对，但替换依据不够稳。",
        "--pitfall", "不要先写成不会再补成半会。",
        "--next-time", "建卡时直接使用真实初始状态。",
        "--check-question", "为什么这题更适合记成半会？",
        "--status", "半会",
        "--comment", "答案能对，但依据还不够稳。",
        "--today", "2026-03-23",
    ])

    assert rc == 0
    card_path = Path(json.loads(out)["path"])
    content = card_path.read_text(encoding="utf-8")
    assert "status: 半会" in content
    assert "#status/半会" in content
    assert "- 2026-03-23 - 半会 - 答案能对，但依据还不够稳。" in content
    assert "- 2026-03-23 - 不会 -" not in content


def test_create_wrong_card_rejects_inline_display_math_in_explanation(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "曲线凹凸性、拐点与渐近线",
        "--topic", "行内块公式风格",
        "--source", "李林",
        "--question-id", "qid-fedcba654321",
        "--question", "求极限并说明理由。",
        "--point-judgment", "这题关键在于 $$x^2$$ 主项。",
        "--first-step", "先识别结构。",
        "--formal-solution", "按主项展开。",
        "--mistake-analysis", "把块公式塞进句子里了。",
        "--pitfall", "句中公式应用 $...$。",
        "--next-time", "块公式单独成行。",
        "--check-question", "为什么这里不该用块公式？",
        "--today", "2026-03-23",
    ])

    assert rc == 1
    data = json.loads(out)
    assert "块公式嵌进了解释句中" in data["message"]
    assert "--point-judgment" in data["message"]


def test_create_wrong_card_allows_standalone_display_math_lines(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "函数极限",
        "--topic", "独立块公式风格",
        "--source", "李林",
        "--question-id", "qid-abcdef123456",
        "--question", "求极限并说明理由。",
        "--point-judgment", "这题关键在于主项判断。",
        "--first-step", "先识别结构。",
        "--formal-solution", "先得到\n$$x-\\sin x\\sim \\frac{x^3}{6}$$\n再继续收口。",
        "--mistake-analysis", "独立推导式允许用块公式。",
        "--pitfall", "不要把块公式塞进句子里。",
        "--next-time", "解释句用行内公式，推导式单独成行。",
        "--check-question", "为什么这行块公式是允许的？",
        "--today", "2026-03-23",
    ])

    assert rc == 0
    content = Path(json.loads(out)["path"]).read_text(encoding="utf-8")
    assert "$$x-\\sin x\\sim \\frac{x^3}{6}$$" in content


def test_create_wrong_card_renders_408_detailed_sections(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "408",
        "--chapter", "操作系统",
        "--topic", "进程调度",
        "--source", "王道",
        "--question-id", "qid-b1c2d3e4f5a6",
        "--question", "以下关于进程调度的说法，正确的是：",
        "--option", "A. FCFS 总能让平均周转时间最小",
        "--option", "B. 时间片轮转适合交互式系统",
        "--option", "C. SJF 一定不会饥饿",
        "--option", "D. 高响应比优先综合考虑等待时间和服务时间",
        "--point-location", "操作系统；调度策略；中高频；最容易混的是评价指标和适用场景。",
        "--breakthrough", "先抓住调度算法的适用场景和评价指标。",
        "--option-analysis", "A 错在把通常情况说成必然。B 对，因为交互式系统重响应。C 错在忽略长作业饥饿。D 对应高响应比优先的判断逻辑。",
        "--dual-track", "严谨版：时间片轮转强调响应时间。通俗版：大家轮流先上 CPU，谁都别一直等。",
        "--trap", "最常见的坑是把平均周转时间最优当成所有场景都最优。",
        "--knowledge-link", "这个点会和响应时间、周转时间、抢占式调度一起考。",
        "--memory-hook", "交互看响应，吞吐看整体。",
        "--check-question", "如果题干改成批处理系统，优先判断轴会变吗？",
        "--today", "2026-03-23",
    ])

    assert rc == 0
    content = Path(json.loads(out)["path"]).read_text(encoding="utf-8")
    assert "### 考点定位" in content
    assert "### 题干突破口" in content
    assert "### 选项逐个辨析" in content
    assert "### 双轨解释" in content
    assert "### 干扰项陷阱" in content
    assert "### 知识网络串联" in content
    assert "### 记忆钩子" in content
    assert "### 检查你是否真的懂了" in content
    assert "交互看响应，吞吐看整体。" in content


def test_create_wrong_card_requires_complete_math_details(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "函数单调性、极值与最值",
        "--topic", "导数应用",
        "--source", "660题",
        "--question-id", "qid-0f1e2d3c4b5a",
        "--question", "已知函数单调，判断极值点存在条件。",
        "--point-judgment", "先判断题型再找对应工具。",
        "--first-step", "先回顾极值判定的基本条件。",
        "--formal-solution", "先列条件，再判断导数符号变化。",
        "--mistake-analysis", "把必要条件当成充分条件了。",
        "--pitfall", "不要只看驻点，不看左右符号。",
        "--today", "2026-03-23",
    ])

    assert rc == 1
    data = json.loads(out)
    assert "--next-time" in data["message"]
    assert "--check-question" in data["message"]


def test_create_wrong_card_rejects_unwrapped_math_formula(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "曲线凹凸性、拐点与渐近线",
        "--topic", "凹凸性",
        "--source", "900题",
        "--question-id", "qid-1234abcd5678",
        "--question", "若 f''(x) > 0，判断函数图像的凹凸性。",
        *required_detail_args("数学一"),
        "--today", "2026-03-23",
    ])

    assert rc == 1
    data = json.loads(out)
    assert "$...$" in data["message"]
    assert "--question" in data["message"]


def test_create_wrong_card_accepts_wrapped_math_formula(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "曲线凹凸性、拐点与渐近线",
        "--topic", "凹凸性",
        "--source", "900题",
        "--question-id", "qid-8765dcba4321",
        "--question", "若 $f''(x) > 0$，判断函数图像的凹凸性。",
        "--point-judgment", "看到 $f''(x) > 0$，先联想到凹凸性判定。",
        "--first-step", "先回忆二阶导数与凹凸性的对应关系。",
        "--formal-solution", "由 $f''(x) > 0$ 可知函数在对应区间上是凸的。",
        "--mistake-analysis", "常见错误是把 $f''(x) > 0$ 和单调性混为一谈。",
        "--pitfall", "不要把二阶导数判定直接套到一阶导数结论上。",
        "--next-time", "下次先分清单调性和凹凸性分别看哪一阶导数。",
        "--check-question", "如果改成 $f''(x) < 0$，图像性质会怎么变？",
        "--today", "2026-03-23",
    ])

    assert rc == 0
    content = Path(json.loads(out)["path"]).read_text(encoding="utf-8")
    assert "$f''(x) > 0$" in content


def test_sanitize_tag_value_truncates_long_values():
    value = sanitize_tag_value("Queue Scheduling Breadth First Search Fairness Analysis")

    assert len(value) <= 32


def test_create_wrong_card_rejects_duplicate_options_double_passed(vault_root):
    """题面已含 A/B/C/D，又通过 --option 显式传同一组选项 → 必须 fail fast，
    否则同一组选项会在 ### 题目 区块重复落盘。"""
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "408",
        "--chapter", "操作系统",
        "--topic", "进程调度",
        "--source", "王道",
        "--question-id", "qid-ddee7788ee99",
        "--question", (
            "下列关于进程调度的说法，正确的是：\n"
            "A. FCFS 总能让平均周转时间最小\n"
            "B. 时间片轮转适合交互式系统\n"
            "C. SJF 一定不会饥饿\n"
            "D. 高响应比优先综合考虑等待时间和服务时间"
        ),
        "--option", "A. FCFS 总能让平均周转时间最小",
        "--option", "B. 时间片轮转适合交互式系统",
        "--option", "C. SJF 一定不会饥饿",
        "--option", "D. 高响应比优先综合考虑等待时间和服务时间",
        "--today", "2026-05-14",
    ])

    assert rc == 1
    data = json.loads(out)
    assert data.get("error") is True
    msg = data.get("message", "")
    assert "题面与显式选项重复" in msg
    assert "二选一" in msg
    assert "A. FCFS 总能让平均周转时间最小" in msg


def test_create_wrong_card_rejects_dense_point_judgment(vault_root):
    """考点判断把多个结构化字段塞进同一行 → 拒绝落盘，提示拆成多行。"""
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "数列极限",
        "--topic", "拥挤考点判断",
        "--source", "李林",
        "--question-id", "qid-aa11bb22cc33",
        "--question", "求该数列的极限。",
        *required_detail_args("数学一"),
        "--point-judgment",
        "题型：不定积分。章节：不定积分计算。考点：分部积分。难度：中等。考频：常见。突破口：先换元。",
        "--today", "2026-03-23",
    ])

    assert rc == 1
    data = json.loads(out)
    assert "排版过密" in data["message"]
    assert "--point-judgment" in data["message"]


def test_create_wrong_card_rejects_overlong_detail_line(vault_root):
    """单条详解行散文过长（>120 字，LaTeX 不计）→ 拒绝落盘。"""
    overlong = "这一步要先观察题目结构再联想可以调用的定理并逐条核对条件是否满足然后代入验证最后才能决定走哪条路" * 3
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "数列极限",
        "--topic", "超长详解行",
        "--source", "李林",
        "--question-id", "qid-dd44ee55ff66",
        "--question", "求该数列的极限。",
        *required_detail_args("数学一"),
        "--first-step", overlong,
        "--today", "2026-03-23",
    ])

    assert rc == 1
    data = json.loads(out)
    assert "排版过密" in data["message"]
    assert "--first-step" in data["message"]


def test_create_wrong_card_rejects_single_line_formal_solution_too_long(vault_root):
    """规范解法挤成一行且散文过长（>80 字）→ 拒绝落盘，提示拆成步骤。"""
    one_liner = "先换元再分部最后回代每一步的依据都要写清楚但这里把整段推导全压成了一行没有分层" * 2 + "完全没有分层很难复习"
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "数列极限",
        "--topic", "规范解法挤成一行",
        "--source", "李林",
        "--question-id", "qid-778899aabbcc",
        "--question", "求该数列的极限。",
        *required_detail_args("数学一"),
        "--formal-solution", one_liner,
        "--today", "2026-03-23",
    ])

    assert rc == 1
    data = json.loads(out)
    assert "规范解法排版过密" in data["message"]


def test_create_wrong_card_accepts_structured_multiline_point_judgment(vault_root):
    """逐字段分行的考点判断应通过，且每个字段单独成一条 bullet。"""
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "数列极限",
        "--topic", "结构化考点判断",
        "--source", "李林",
        "--question-id", "qid-123abc456def",
        "--question", "求该数列的极限。",
        "--point-judgment",
        "题型：反三角函数复合不定积分\n"
        "章节：不定积分的计算\n"
        "考点：反三角整体换元、三角恒等变形、分部积分\n"
        "难度：中等\n"
        "考频：常见模型\n"
        "突破口：令 $t=\\arctan x$，把代数结构转成三角结构",
        "--first-step", "先看结构，判断能否整体换元。",
        "--formal-solution", "先令 $t=\\arctan x$，再分部积分。",
        "--mistake-analysis", "容易忘记先比较换元与分部的复杂度。",
        "--pitfall", "$\\cot^2t$ 先写成 $\\csc^2t-1$。",
        "--next-time", "下次先判断整体换元能否约掉代数结构。",
        "--check-question", "为什么令 $t=\\arctan x$ 后分母会约掉？",
        "--today", "2026-03-23",
    ])

    assert rc == 0
    content = Path(json.loads(out)["path"]).read_text(encoding="utf-8")
    assert "- 题型：反三角函数复合不定积分" in content
    assert "- 章节：不定积分的计算" in content
    assert "- 突破口：令 $t=\\arctan x$，把代数结构转成三角结构" in content


def test_create_wrong_card_formal_solution_preserves_block_math_without_bullets(vault_root):
    """规范解法保留 Markdown 原文：多行块公式不被加 `- `，Obsidian 才能渲染。"""
    formal = (
        "先令 $t=\\arctan x$，则 $x=\\tan t$。\n"
        "$$\n"
        "I=\\int t\\cot^2t\\,dt.\n"
        "$$\n"
        "再用 $\\cot^2t=\\csc^2t-1$ 继续。"
    )
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "数列极限",
        "--topic", "块公式保留",
        "--source", "李林",
        "--question-id", "qid-beef0011cafe",
        "--question", "求该数列的极限。",
        "--point-judgment", "题型：换元降维题。",
        "--first-step", "先看结构再换元。",
        "--formal-solution", formal,
        "--mistake-analysis", "把块公式塞进 bullet 会破坏渲染。",
        "--pitfall", "块公式必须独立成行。",
        "--next-time", "规范解法直接传多行结构。",
        "--check-question", "为什么块公式不能被加 `- `？",
        "--today", "2026-03-23",
    ])

    assert rc == 0
    content = Path(json.loads(out)["path"]).read_text(encoding="utf-8")
    formal_block = extract_heading_block(content, "规范解法", level=3)
    assert "- $$" not in formal_block
    assert "$$\nI=\\int t\\cot^2t\\,dt.\n$$" in formal_block
    assert "I=\\int t\\cot^2t\\,dt." in formal_block


def test_create_wrong_card_formal_solution_airy_layout(vault_root):
    """规范解法落盘即疏朗：紧凑多行输入 → 每步/每段块公式之间补恰好一个空行。"""
    formal = (
        "取 $u=\\arctan\\sqrt{e^x-1}$，则 $v=\\tfrac12 e^{2x}$。\n"
        "$$\n"
        "I=\\tfrac12 e^{2x}\\arctan\\sqrt{e^x-1}.\n"
        "$$\n"
        "令 $t=\\sqrt{e^x-1}$。\n"
        "$$\n"
        "\\int=\\tfrac23 t^3+2t.\n"
        "$$\n"
        "回代即得最终结果。"
    )
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "数列极限",
        "--topic", "疏朗版式",
        "--source", "李林",
        "--question-id", "qid-aaaa11112222",
        "--question", "求该积分。",
        *required_detail_args("数学一"),
        "--formal-solution", formal,
        "--today", "2026-03-23",
    ])

    assert rc == 0
    content = Path(json.loads(out)["path"]).read_text(encoding="utf-8")
    formal_block = extract_heading_block(content, "规范解法", level=3)
    # 块公式前后必有空行；步骤之间也有空行；但块内部仍单 \n 连续
    assert "。\n\n$$" in formal_block
    assert "$$\n\n令 $t=\\sqrt{e^x-1}$。" in formal_block
    assert "$$\n\n回代即得最终结果。" in formal_block
    assert "$$\nI=\\tfrac12 e^{2x}\\arctan\\sqrt{e^x-1}.\n$$" in formal_block
    # 不出现三连空行
    assert "\n\n\n" not in formal_block


def test_create_wrong_card_formal_solution_spacing_idempotent(vault_root):
    """模型已按疏朗风格留了空行：脚本归一为恰好单空行，不叠成三连空行。"""
    formal = (
        "先令 $t=\\arctan x$。\n"
        "\n"
        "$$\n"
        "I=\\int t\\cot^2t\\,dt.\n"
        "$$\n"
        "\n"
        "再用恒等式收口。"
    )
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "数列极限",
        "--topic", "空行归一",
        "--source", "李林",
        "--question-id", "qid-bbbb33334444",
        "--question", "求该积分。",
        *required_detail_args("数学一"),
        "--formal-solution", formal,
        "--today", "2026-03-23",
    ])

    assert rc == 0
    content = Path(json.loads(out)["path"]).read_text(encoding="utf-8")
    formal_block = extract_heading_block(content, "规范解法", level=3)
    assert "\n\n\n" not in formal_block
    assert "先令 $t=\\arctan x$。\n\n$$" in formal_block
    assert "$$\n\n再用恒等式收口。" in formal_block


def test_create_wrong_card_rejects_inline_math_wall_formal_solution(vault_root):
    """规范解法挤成一行连排多段行内 $...$（行内公式墙）→ 拒绝落盘，提示拆步骤。"""
    wall = (
        "取 $u=\\arctan\\sqrt{e^x-1}$，$dv=e^{2x}dx$，则 $v=\\frac{1}{2}e^{2x}$。"
        "设 $y=\\sqrt{e^x-1}$，则 $1+y^2=e^x$，所以 $u'=\\frac{1}{2\\sqrt{e^x-1}}$。"
    )
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "数列极限",
        "--topic", "行内公式墙",
        "--source", "李林",
        "--question-id", "qid-cccc55556666",
        "--question", "求该积分。",
        *required_detail_args("数学一"),
        "--formal-solution", wall,
        "--today", "2026-03-23",
    ])

    assert rc == 1
    data = json.loads(out)
    assert "规范解法排版过密" in data["message"]
    assert "行内" in data["message"]


# ---------- 配图 ----------

FIGURE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 320">
  <style>:root{--ink:#1f2933;--bg:#fdfdfb}
  @media (prefers-color-scheme: dark){:root{--ink:#e6e8eb;--bg:#1e1f22}}
  text{font-family:Arial,sans-serif;font-size:14px}
  .bg{fill:var(--bg)} .ink{fill:var(--ink)}</style>
  <rect class="bg" width="480" height="320" fill="#fdfdfb"/>
  <text class="ink" x="40" y="40" fill="#1f2933">D</text>
</svg>"""


def make_figure(vault_root, question_id, slug="积分区域", caption="图1：原积分区域 D"):
    """落一张真图，返回可直接传给 --figure 的 figure_arg。"""
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


def create_card(vault_root, subject, question_id, chapter, extra=None):
    return run_script("create_wrong_card.py", [
        str(vault_root), subject,
        "--chapter", chapter,
        "--topic", "配图测试",
        "--source", "900题",
        "--question-id", question_id,
        "--question", "题面正文。",
    ] + required_detail_args(subject) + (extra or []))


def test_math_figure_section_sits_between_first_step_and_formal_solution(vault_root):
    qid = "qid-a1b2c3d4e5f6"
    figure_arg = make_figure(vault_root, qid)
    rc, out, err = create_card(vault_root, "数学一", qid, "数列极限", ["--figure", figure_arg])
    assert rc == 0, out + err
    payload = json.loads(out)
    assert payload["figure_count"] == 1
    text = Path(payload["path"]).read_text(encoding="utf-8")
    assert "### 图示" in text
    assert text.index("### 第一步怎么想到") < text.index("### 图示") < text.index("### 规范解法")
    assert "![[错题本/_附图/qid-a1b2c3d4e5f6/qid-a1b2c3d4e5f6-01-积分区域.svg|480]]" in text
    assert "- 图1：原积分区域 D" in text


def test_408_figure_section_sits_between_breakthrough_and_option_analysis(vault_root):
    qid = "qid-b1b2c3d4e5f6"
    figure_arg = make_figure(vault_root, qid, slug="位段图", caption="图1：Cache 地址位段划分")
    rc, out, err = create_card(vault_root, "408", qid, "数据结构", ["--figure", figure_arg])
    assert rc == 0, out + err
    text = Path(json.loads(out)["path"]).read_text(encoding="utf-8")
    assert text.index("### 题干突破口") < text.index("### 图示") < text.index("### 选项逐个辨析")


def test_no_figure_section_when_no_figure_passed(vault_root):
    rc, out, err = create_card(vault_root, "数学一", "qid-c1b2c3d4e5f6", "数列极限")
    assert rc == 0, out + err
    payload = json.loads(out)
    assert payload["figure_count"] == 0
    assert "### 图示" not in Path(payload["path"]).read_text(encoding="utf-8")


def test_question_figure_lands_in_question_block(vault_root):
    qid = "qid-d1b2c3d4e5f6"
    figure_arg = make_figure(vault_root, qid, slug="题面图", caption="图0：题面所给几何图")
    rc, out, err = create_card(vault_root, "数学一", qid, "数列极限", ["--question-figure", figure_arg])
    assert rc == 0, out + err
    payload = json.loads(out)
    assert payload["question_figure_count"] == 1
    text = Path(payload["path"]).read_text(encoding="utf-8")
    question_block = extract_heading_block(text, "题目", level=3)
    assert "图0：题面所给几何图" in question_block
    assert "### 图示" not in text


def test_rejects_missing_figure_file(vault_root):
    rc, out, _ = create_card(
        vault_root, "数学一", "qid-e1b2c3d4e5f6", "数列极限",
        ["--figure", "错题本/_附图/qid-e1b2c3d4e5f6/不存在.svg|图1：不存在"],
    )
    assert rc == 1
    assert "配图不存在" in json.loads(out)["message"]


def test_rejects_figure_outside_vault(vault_root, tmp_path):
    # vault_root fixture 就是 tmp_path 本身，所以「vault 外」要往上一层放
    outside = tmp_path.parent / "outside.svg"
    outside.write_text(FIGURE_SVG, encoding="utf-8")
    rc, out, _ = create_card(
        vault_root, "数学一", "qid-f1b2c3d4e5f6", "数列极限",
        ["--figure", f"{outside}|图1：越界"],
    )
    assert rc == 1
    assert "vault 之外" in json.loads(out)["message"]


def test_rejects_non_svg_figure(vault_root):
    png = vault_root / "错题本" / "fake.png"
    png.write_text("not really a png", encoding="utf-8")
    rc, out, _ = create_card(
        vault_root, "数学一", "qid-01b2c3d4e5f6", "数列极限",
        ["--figure", "错题本/fake.png|图1：位图"],
    )
    assert rc == 1
    assert "只接受 .svg" in json.loads(out)["message"]


def test_rejects_malformed_figure_spec(vault_root):
    rc, out, _ = create_card(
        vault_root, "数学一", "qid-11b2c3d4e5f6", "数列极限",
        ["--figure", "只有路径没有说明.svg"],
    )
    assert rc == 1
    assert "格式应为" in json.loads(out)["message"]
