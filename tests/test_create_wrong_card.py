"""test create_wrong_card.py"""
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from archive_ops import extract_heading_block
from create_wrong_card import sanitize_tag_value
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
    assert card_path.parent == (
        vault_root
        / "错题本"
        / "数学一"
        / "高等数学"
        / "01第一章函数、极限、连续"
        / "03第三节数列极限"
    )


def test_create_wrong_card_falls_back_to_single_level_when_chapter_unmapped(vault_root):
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

    assert rc == 0
    data = json.loads(out)
    card_path = Path(data["path"])
    assert card_path.parent == vault_root / "错题本" / "数学一" / "未配置章节"


def test_create_wrong_card_reports_unknown_subject_instead_of_treating_it_as_root(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        "数学二",
        "--chapter", "高等数学",
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
        "--chapter", "高等数学",
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
        "--chapter", "高等数学",
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
        "--chapter", "高等数学",
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
        "--chapter", "高等数学",
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
        "--chapter", "高等数学",
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
        "--chapter", "高等数学",
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
        "--chapter", "高等数学",
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
        "--chapter", "高等数学",
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
