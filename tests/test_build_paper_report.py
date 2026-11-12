"""测试套卷深度复盘脚本 build_paper_report.py。"""
import json
from pathlib import Path

import pytest

from helpers import run_script
from test_create_wrong_card import required_detail_args
from wrong_card_path_map import resolve_wrong_card_chapter


def run(name, args):
    rc, out, err = run_script(name, args)
    assert rc == 0, out + err
    return json.loads(out)


def make_math_card(
    root,
    qid_num,
    question_number,
    paper,
    chapter="二重积分",
    topic="二重积分换序",
    day="2026-10-12",
    error_type="思路偏差",
):
    return run(
        "create_wrong_card.py",
        [
            str(root),
            "数学一",
            "--chapter",
            chapter,
            "--topic",
            topic,
            "--source",
            paper,
            "--question-id",
            f"qid-{qid_num:012x}",
            "--question",
            f"第{question_number}题：计算积分。",
            "--question-number",
            str(question_number),
            "--error-type",
            error_type,
            "--today",
            day,
            *required_detail_args("数学一"),
        ],
    )


def test_math1_paper_report_merges_cards_manual_losses_clusters_and_load_context(sample_archive, vault_root):
    # 1. 前序套卷（10-10）：第 3 题二重积分出错
    make_math_card(
        vault_root,
        qid_num=1,
        question_number=3,
        paper="2026李林六套卷(一)",
        chapter="二重积分",
        topic="二重积分换序",
        day="2026-10-10",
        error_type="没思路",
    )
    run(
        "record_paper_score.py",
        [
            str(vault_root),
            "数学一",
            "--paper",
            "2026李林六套卷(一)",
            "--paper-type",
            "模拟",
            "--total",
            "105",
            "--score-objective",
            "60",
            "--score-big",
            "45",
            "--date",
            "2026-10-10",
        ],
    )

    # 2. 立项一个泰勒公式突破单（在本卷未再犯，验证阶段止血信号）
    taylor_cid = resolve_wrong_card_chapter("数学一", "洛必达法则与泰勒展开求极限", strict=True).chapter_id
    run(
        "manage_breakthrough.py",
        [
            "create",
            str(vault_root),
            "--goal",
            "泰勒展开求极限",
            "--source",
            "阶段测试",
            "--plan",
            "Day1：重做;Day2：变式;Day3：验收",
            "--criteria",
            "3对3",
            "--today",
            "2026-10-11",
            "--topic-id",
            taylor_cid,
        ],
    )

    # 3. 本卷（10-12）：
    # - /score 轻量记录第 6 题（计算失误）、第 12 题（时间不够）
    # - /wrong 归档第 3 题（同日）、第 22 题（隔日 10-13 补录）
    make_math_card(
        vault_root,
        qid_num=3,
        question_number=3,
        paper="2026李林六套卷(二)",
        chapter="二重积分",
        topic="二重积分换序",
        day="2026-10-12",
        error_type="思路偏差",
    )
    make_math_card(
        vault_root,
        qid_num=22,
        question_number=22,
        paper="2026李林六套卷(二)",
        chapter="点估计",
        topic="最大似然估计",
        day="2026-10-13",
        error_type="遗忘",
    )
    run(
        "record_paper_score.py",
        [
            str(vault_root),
            "数学一",
            "--paper",
            "2026李林六套卷(二)",
            "--paper-type",
            "模拟",
            "--total",
            "118",
            "--score-objective",
            "65",
            "--score-big",
            "53",
            "--date",
            "2026-10-12",
            "--wrong-questions",
            "6:计算失误;12:时间不够",
            "--question-topics",
            "6:矩阵的秩;12:反常积分",
        ],
    )

    # 4. 写入元技能索引，把 qid-1 与 qid-3 归入同一元技能簇
    index_path = vault_root / "错题本" / "_元技能索引.json"
    index_path.write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "id": "m01-积分换序",
                        "name": "二重积分画域换序",
                        "skill": "看到什么：\n1. 被积函数不可积\n怎么做：\n1. 先画积分域再换序",
                        "qids": ["000000000001", "000000000003"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # 5. 首次生成套卷深度复盘报告：应进入 analyze 模式
    report_data = run(
        "build_paper_report.py",
        [str(vault_root), "数学一", "--paper", "2026李林六套卷(二)"],
    )
    assert report_data["mode"] == "analyze"
    assert report_data["report_existed"] is False

    report_path = Path(report_data["report_path"])
    assert report_path.exists()
    assert report_path.parent.name == "复盘报告"
    assert report_path.name.endswith("-套卷分析.md")

    # 6. 再次对同一套已复盘过的试卷调用：自动切换为 review（本卷错题二刷）模式，返回 review_queue
    review_data = run(
        "build_paper_report.py",
        [str(vault_root), "数学一", "--paper", "2026李林六套卷(二)"],
    )
    assert review_data["mode"] == "review"
    assert review_data["report_existed"] is True
    assert review_data["review_summary"]["total_card_count"] == 2
    assert review_data["review_summary"]["pending_count"] == 2
    assert [item["question_number"] for item in review_data["review_queue"]] == [3, 22]
    assert "第3题：计算积分" in review_data["review_queue"][0]["question_text"]

    # 7. 当不传 --paper 时：因为六套卷(二)已复盘，而六套卷(一)尚未生成复盘报告，应优先定位未复盘的六套卷(一)
    auto_unanalyzed = run("build_paper_report.py", [str(vault_root), "数学一"])
    assert auto_unanalyzed["paper"] == "2026李林六套卷(一)"
    assert auto_unanalyzed["mode"] == "analyze"
    assert auto_unanalyzed["report_existed"] is False

    # 8. 当所有已记录试卷均已生成过复盘报告后，再省略 --paper 调用：定位最新试卷并进入 review 模式
    auto_review = run("build_paper_report.py", [str(vault_root), "数学一"])
    assert auto_review["paper"] == "2026李林六套卷(二)"
    assert auto_review["mode"] == "review"
    assert auto_review["report_existed"] is True

    # 验证 4 道错题（2 张错题卡 + 2 道轻量记录粗心题）全部合入
    q_nums = [q["question_number"] for q in report_data["wrong_questions"]]
    assert q_nums == [3, 6, 12, 22]
    assert report_data["linked_card_count"] == 2
    assert report_data["repeat_offender_count"] == 1
    assert report_data["first_time_count"] == 3

    # 验证第 3 题穿透出历史惯犯与同元技能簇兄弟卡
    q3 = next(q for q in report_data["wrong_questions"] if q["question_number"] == 3)
    assert q3["is_repeat_offender"] is True
    assert q3["total_occurrences"] == 2
    assert q3["cluster"]["id"] == "m01-积分换序"
    assert q3["cluster"]["sibling_links"]
    assert q3["action_hook"]

    # 验证失分账本：第 6、12 题为新制选填（各 5 分），确定性冤枉失分 = 10 分，保底潜力分 = 128 分
    ledger = report_data["loss_ledger"]
    assert ledger["confirmed_regret_objective_loss"] == pytest.approx(10.0)
    assert ledger["potential_score_floor"] == pytest.approx(128.0)

    # 验证稳固阵地（选填得分率 65/80 = 81.25% >= 80%）与突破单止血信号
    assert any("选填题得分率达 81.2%" in s for s in report_data["strengths"])
    assert any("泰勒展开求极限" in s for s in report_data["stopped_bleeding"])

    # 验证 Markdown 报告包含关键区块且可被 load_context.py 识别
    md_text = report_path.read_text(encoding="utf-8")
    assert "## 卷面基本盘与优势阵地" in md_text
    assert "## 失分账本：硬伤分 vs 冤枉分" in md_text
    assert "## 错题深度串联：惯犯 vs 初犯" in md_text
    assert "## 本卷考前复盘口诀清单" in md_text
    assert "## 关键问题" in md_text
    assert "## 下一步动作" in md_text

    load_data = run("load_context.py", [str(vault_root), "--today", "2026-10-12"])
    assert load_data["latest_report_path"] == str(report_path)


def test_408_one_step_score_and_report_with_module_warnings(sample_archive, vault_root):
    result = run(
        "build_paper_report.py",
        [
            str(vault_root),
            "408",
            "--paper",
            "王道八套卷(一)",
            "--paper-type",
            "模拟",
            "--total",
            "108",
            "--date",
            "2026-10-15",
            "--score-choice-ds",
            "20",
            "--score-big-ds",
            "20",
            "--score-choice-co",
            "12",
            "--score-big-co",
            "10",
            "--score-choice-os",
            "16",
            "--score-big-os",
            "12",
            "--score-choice-cn",
            "12",
            "--score-big-cn",
            "6",
            "--wrong-questions",
            "13:计算失误;43:没思路",
            "--question-topics",
            "13:IEEE754浮点数;43:Cache组相联映射",
        ],
    )
    assert Path(result["score_record_path"]).exists()
    assert Path(result["report_path"]).exists()
    assert any("DS" in s for s in result["strengths"])
    assert any("CO得分率偏低" in issue for issue in result["key_issues"])
    assert result["loss_ledger"]["confirmed_regret_objective_loss"] == pytest.approx(2.0)
    assert result["loss_ledger"]["potential_score_floor"] == pytest.approx(110.0)


def test_dry_run_and_objective_section_isolation(sample_archive, vault_root):
    preview = run(
        "build_paper_report.py",
        [
            str(vault_root),
            "--subject",
            "数学",
            "--section",
            "选填",
            "--paper",
            "2018真题",
            "--paper-type",
            "真题",
            "--total",
            "48",
            "--date",
            "2026-10-16",
            "--wrong-questions",
            "4:算错;13:遗忘",
            "--question-topics",
            "4:导数定义;13:特征值",
            "--dry-run",
        ],
    )
    assert preview["dry_run"] is True
    assert not Path(preview["report_path"]).exists()
    # 2018 旧制真题选填满分 56，单题 4 分
    assert preview["loss_ledger"]["max_score"] == pytest.approx(56.0)
    assert preview["loss_ledger"]["confirmed_regret_objective_loss"] == pytest.approx(4.0)
    assert preview["loss_ledger"]["potential_score_floor"] == pytest.approx(52.0)
