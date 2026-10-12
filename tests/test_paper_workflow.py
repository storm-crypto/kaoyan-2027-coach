"""第三批工作流：自动关联、结构化信号、对口验收与只读纵向数据。"""
import json
from datetime import date
from pathlib import Path

import pytest

from helpers import run_script
from breakthrough_ops import parse_breakthroughs
from frontmatter import parse_frontmatter
from manage_breakthrough import close, create, update_status
from score_record_lib import parse_score_record
from test_create_wrong_card import required_detail_args
from wrong_card_path_map import resolve_wrong_card_chapter


DAY = "2026-10-12"
PLAN = "Day1：重做;Day2：变式;Day3：/test 验收"


def run(name, args):
    rc, out, err = run_script(name, args)
    assert rc == 0, out + err
    return json.loads(out)


def make_card(root, number=3, paper="测试卷", topic="二重积分", day=DAY, extra=(), question=None):
    result = run("create_wrong_card.py", [str(root), "数学一", "--chapter", "二重积分", "--topic", topic,
        "--source", paper, "--question-id", f"qid-{number:012x}", "--question", question or "请计算题目所给积分。",
        "--question-number", str(number), "--today", day, *required_detail_args("数学一"), *extra])
    return Path(result["path"]), result


def record(root, paper="测试卷", day=DAY, total=100, extras=()):
    result = run("record_paper_score.py", [str(root), "数学一", "--paper", paper, "--paper-type", "真题",
        "--total", str(total), "--date", day, *extras])
    return parse_score_record(Path(result["record_path"])), result


def check(root, today=DAY):
    return run("check_breakthrough_triggers.py", [str(root), "--today", today])


def test_score_links_two_cards_and_old_23_question_without_touching_cards(sample_archive, vault_root):
    first, _ = make_card(vault_root, 3, paper="2010测试卷")
    second, _ = make_card(vault_root, 23, paper="2010测试卷", extra=["--error-type", "遗忘"])
    make_card(vault_root, 8, paper="测试卷二刷")
    make_card(vault_root, 12, paper="2010测试卷", day="2026-10-11")
    before = {path: path.read_bytes() for path in (first, second)}
    stored, output = record(vault_root, paper="2010测试卷")
    errors = stored["wrong_questions"]
    assert [(q["question_number"], q["topic"]) for q in errors] == [(3, "二重积分"), (23, "二重积分")]
    assert errors[1]["error_type"] == "遗忘"
    assert errors[0]["question_id"] == "qid-000000000003"
    assert output["linked_question_count"] == 2 and output["wrong_questions_mode"] == "auto"
    assert all(path.read_bytes() == content for path, content in before.items())
    assert record(vault_root, paper="2010测试卷")[0]["wrong_questions"] == errors


def test_manual_override_replaces_auto_list_and_empty_clears(sample_archive, vault_root):
    make_card(vault_root, 3, paper="2010真题")
    make_card(vault_root, 8, paper="2010真题")
    stored, result = record(vault_root, paper="2010真题", extras=["--wrong-questions", "23:没思路", "--question-topics", "23:概率分布"])
    assert result["wrong_questions_mode"] == "manual"
    assert [q["question_number"] for q in stored["wrong_questions"]] == [23]
    assert stored["wrong_questions"][0]["topic"] == "概率分布"
    assert record(vault_root, paper="2010真题", extras=["--wrong-questions", ""])[0]["wrong_questions"] == []


def test_legacy_number_extraction_and_missing_number_warning(sample_archive, vault_root):
    path, _ = make_card(vault_root, 3, question="第 3 题：计算所给积分。")
    path.write_text(path.read_text().replace("question_number: 3\n", ""))
    missing, _ = make_card(vault_root, 8)
    missing.write_text(missing.read_text().replace("question_number: 8\n", ""))
    stored, result = record(vault_root)
    assert [q["question_number"] for q in stored["wrong_questions"]] == [3]
    assert result["link_warnings"] and "缺少" in result["link_warnings"][0]["reason"]
    assert check(vault_root)["triggered"] == []


def test_source_suffix_and_duplicate_number_reported(sample_archive, vault_root):
    path, _ = make_card(vault_root, 3, paper="测试卷第3题")
    path.write_text(path.read_text().replace("question_number: 3\n", ""))
    assert record(vault_root)[0]["wrong_questions"][0]["question_number"] == 3
    duplicate = path.with_name("另一张.md")
    duplicate.write_text(path.read_text().replace("qid-000000000003", "qid-ffffffffffff"))
    result = record(vault_root)[1]
    assert any("多张" in warning["reason"] for warning in result["link_warnings"])


@pytest.mark.parametrize("kind", ["没思路", "遗忘", "计算失误", "思路偏差", "时间不够"])
def test_error_type_round_trip(vault_root, kind):
    path, result = make_card(vault_root, extra=["--error-type", kind])
    fm, _, _ = parse_frontmatter(path.read_text())
    assert fm["error_type"] == kind and result["error_type"] == kind
    assert fm["consecutive_failures"] == "0"


def test_invalid_error_type_and_number_conflict_do_not_create(vault_root):
    args = [str(vault_root), "数学一", "--chapter", "二重积分", "--topic", "积分", "--source", "测试卷",
        "--question-id", "qid-000000000003", "--question", "第8题：计算积分。", "--question-number", "3",
        *required_detail_args("数学一")]
    rc, out, _ = run_script("create_wrong_card.py", args)
    assert rc == 1 and "冲突" in json.loads(out)["message"]
    rc, _, _ = run_script("create_wrong_card.py", args + ["--error-type", "粗心"])
    assert rc != 0
    assert list((vault_root / "错题本").rglob("*.md")) == []


def test_explicit_23_not_confused_with_subquestion_number(sample_archive, vault_root):
    path, _ = make_card(vault_root, 23, paper="2010 数学一真题", question="(1) 求所给随机变量的分布。")
    fm, _, _ = parse_frontmatter(path.read_text())
    assert fm['question_number'] == '23'
    stored, _ = record(vault_root, paper="2010 数学一真题")
    assert stored['wrong_questions'][0]['question_number'] == 23


def test_auto_association_uses_score_paper_type_for_question_limit(sample_archive, vault_root):
    make_card(vault_root, 23, paper="2010真题")
    result = run('record_paper_score.py', [str(vault_root), '数学一', '--paper', '2010真题',
                 '--paper-type', '模拟', '--date', DAY, '--total', '100'])
    stored = parse_score_record(Path(result['record_path']))
    assert stored['wrong_questions'] == []
    assert '1–22' in result['link_warnings'][0]['reason']


def test_decimal_at_question_start_is_not_a_question_number(vault_root):
    args = [str(vault_root), "数学一", "--chapter", "二重积分", "--topic", "积分", "--source", "测试卷",
        "--question-id", "qid-000000000003", "--question", "3.14 是计算时采用的圆周率近似值，求积分。",
        *required_detail_args("数学一")]
    result = run('create_wrong_card.py', args)
    assert result['question_number'] is None


def test_structured_trigger_deduplicates_score_and_cards(sample_archive, vault_root):
    for number in (3, 8, 23):
        make_card(vault_root, number, paper="2010真题")
    record(vault_root, paper="2010真题")
    result = check(vault_root)
    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["count"] == 3
    assert result["triggered"][0]["topic"] == "二重积分"
    assert result["triggered"][0]["chapter_id"] == "math1:gaoshu:10:02"
    assert "unmapped" not in result


def test_chapter_id_groups_different_topic_labels(vault_root):
    for number, topic in ((3, "极坐标"), (8, "积分换序"), (12, "画区域")):
        make_card(vault_root, number, topic=topic)
    result = check(vault_root)
    assert result["triggered"][0]["count"] == 3
    assert result["triggered"][0]["chapter_id"] == "math1:gaoshu:10:02"


def test_failure_streak_stays_integer_and_triggers_beyond_window(vault_root):
    path, _ = make_card(vault_root, day="2026-10-01")
    for count, day in enumerate(("2026-10-03", "2026-10-06", "2026-10-09"), 1):
        result = run("update_card.py", [str(path), "--status", "不会", "--today", day, "--comment", f"第{count}次复测"])
        assert result["consecutive_failures"] == count
        assert result["interval"] == 1 and result["repeated_failure_signal"] == (count >= 3)
    signals = check(vault_root)
    assert signals["triggered"] == []
    assert signals["strong_signals"][0]["reason"] == "consecutive_failures"
    assert signals["strong_signals"][0]["consecutive_failures"] == 3
    result = run("update_card.py", [str(path), "--status", "半会", "--today", DAY])
    assert result["consecutive_failures"] == 0
    assert not check(vault_root).get("strong_signals")


def test_legacy_history_streak_excludes_initial_and_survives_migration(vault_root):
    path, _ = make_card(vault_root, day="2026-10-01")
    text = path.read_text().replace("consecutive_failures: 0\n", "")
    text += "\n- 2026-10-05 - 不会 - 第一次复习\n- 2026-10-08 - 不会 - 第二次复习\n"
    path.write_text(text)
    assert not check(vault_root).get("strong_signals")
    result = run("update_card.py", [str(path), "--status", "不会", "--today", DAY])
    assert result["consecutive_failures"] == 3


def test_low_module_accuracy_strict_threshold_and_unknown_scores(sample_archive, vault_root):
    record(vault_root, paper="2020边界卷", total=93.6, extras=["--score-objective", "33.6", "--score-big", "60"])
    record(vault_root, paper="2020低分卷", total=93, extras=["--score-objective", "33", "--score-big", "60"])
    record(vault_root, paper="仅总分卷", total=50)
    signals = [signal for signal in check(vault_root).get("strong_signals", []) if signal["reason"] == "module_accuracy"]
    assert [(signal["paper"], signal["module"]) for signal in signals] == [("2020低分卷", "objective")]
    assert signals[0]["accuracy"] == pytest.approx(33 / 56)


def test_breakthrough_topic_ids_persist_through_delay_and_target_mastered_leaf(sample_archive, vault_root):
    topic_id = resolve_wrong_card_chapter("数学一", "二重积分", strict=True).chapter_id
    target_map = vault_root / "知识地图" / "数学一.md"
    target_map.write_text("## 高等数学\n| 考点 | 掌握度 | 信心 | 备注 |\n|---|---|---|---|\n"
        "| **10 第十章 二重积分** | | | |\n| 10.02 第二节 二重积分的计算 | 会 | 高 | |\n"
        "| **03 第三章 微分中值定理与泰勒公式** | | | |\n| 03.04 第四节 泰勒公式 | 不会 | 低 | |\n")
    output = run("manage_breakthrough.py", ["create", str(vault_root), "--goal", "积分验收", "--source", "测试卷",
        "--plan", PLAN, "--criteria", "5对4", "--today", DAY, "--topic-id", topic_id, "--topic-id", topic_id])
    item_id = output["id"]
    assert parse_breakthroughs(sample_archive.read_text())[0]["topic_ids"] == [topic_id]
    update_status(vault_root, item_id, 3)
    close(vault_root, item_id, "延期")
    assert parse_breakthroughs(sample_archive.read_text())[0]["topic_ids"] == [topic_id]
    before = sample_archive.read_bytes(), target_map.read_bytes()
    result = run("build_knowledge_test.py", [str(vault_root), "数学一", "--breakthrough-id", item_id, "--count", "1"])
    assert result["questions"][0]["topic_id"] == topic_id
    assert result["questions"][0]["source_mastery"] == "会"
    assert before == (sample_archive.read_bytes(), target_map.read_bytes())
    normal = run("build_knowledge_test.py", [str(vault_root), "数学一", "--count", "1"])
    assert "泰勒" in normal["questions"][0]["topic"]


def test_missing_breakthrough_ids_do_not_silently_test_other_topics(sample_archive, vault_root):
    (vault_root / "知识地图" / "数学一.md").write_text("## 高等数学\n| 考点 | 掌握度 | 信心 | 备注 |\n| 10.02 第二节 二重积分的计算 | 不会 | 低 | |\n")
    item_id = create(vault_root, "目标", "来源", PLAN, "标准", today=date.fromisoformat(DAY))["id"]
    rc, out, _ = run_script("build_knowledge_test.py", [str(vault_root), "数学一", "--breakthrough-id", item_id])
    assert rc == 1 and "topic_ids" in json.loads(out)["message"]


def test_analyze_three_papers_outputs_ordered_scores_modules_and_topic_counts_read_only(sample_archive, vault_root):
    for paper, day, objective, big, errors, topics in [
        ("2012卷", "2026-10-12", 50, 80, "", None),
        ("2010卷", "2026-10-10", 30, 60, "3:不会;23:忘记", "3:积分;23:积分"),
        ("2011卷", "2026-10-11", 40, 70, "8:算错", "8:积分"),
    ]:
        extras = ["--score-objective", str(objective), "--score-big", str(big), "--wrong-questions", errors]
        if topics:
            extras += ["--question-topics", topics]
        record(vault_root, paper, day, objective + big, extras)
    before = {path: path.read_bytes() for path in vault_root.rglob("*.md")}
    result = run("analyze_paper.py", [str(vault_root), "--subject", "数学一"])
    assert [paper["paper"] for paper in result["papers"]] == ["2010卷", "2011卷", "2012卷"]
    assert [paper["total_score"] for paper in result["papers"]] == [90, 110, 130]
    assert result["papers"][0]["modules"]["objective"]["accuracy"] == pytest.approx(30 / 56)
    assert result["papers"][0]["modules"]["big"]["accuracy"] == pytest.approx(60 / 94)
    series = result["topic_wrong_count_series"]
    assert series[0]["topic"] == "积分"
    assert [point["wrong_count"] for point in series[0]["sequence"]] == [2, 1, 0]
    assert "accuracy" not in series[0]
    assert {path: path.read_bytes() for path in vault_root.rglob("*.md")} == before
    filtered = run("analyze_paper.py", [str(vault_root), "--subject", "数学", "--start-date", "2026-10-11", "--end-date", DAY])
    assert len(filtered["papers"]) == 2
    assert run("analyze_paper.py", [str(vault_root), "--subject", "数学一", "--paper", "2010卷"])["papers"][0]["total_score"] == 90
    assert run("analyze_paper.py", [str(vault_root), "--subject", "数学一", "--paper", "2010"])["papers"] == []


def test_408_eight_scores_and_four_module_rates_and_partial_data(sample_archive, vault_root):
    args = [str(vault_root), "408", "--paper", "408测试卷", "--paper-type", "模拟", "--total", "112", "--date", DAY,
        "--score-choice-ds", "10", "--score-big-ds", "13", "--score-choice-co", "18", "--score-big-co", "20",
        "--score-choice-os", "16", "--score-big-os", "13", "--score-choice-cn", "14", "--score-big-cn", "8"]
    run("record_paper_score.py", args)
    run("record_paper_score.py", [str(vault_root), "408", "--paper", "未报齐", "--paper-type", "模拟", "--total", "80",
                                  "--date", DAY, "--score-choice-ds", "10"])
    result = run("analyze_paper.py", [str(vault_root), "--subject", "408", "--paper", "408测试卷"])
    modules = result["papers"][0]["modules"]
    assert modules["DS"] == {"choice": 10, "big": 13, "score": 23, "max_score": 45, "accuracy": 23 / 45}
    assert modules["CO"]["choice"] == 18 and modules["CO"]["big"] == 20
    assert modules["OS"]["accuracy"] == 29 / 35 and modules["CN"]["accuracy"] == 22 / 25
    partial = run("analyze_paper.py", [str(vault_root), "--subject", "408", "--paper", "未报齐"])
    assert "accuracy" not in partial["papers"][0]["modules"]["DS"]
    signals = check(vault_root)["strong_signals"]
    assert len(signals) == 1 and signals[0]["module"] == "DS" and signals[0]["paper"] == "408测试卷"


def test_analyzer_honors_manual_clear_and_rejects_reversed_range(sample_archive, vault_root):
    make_card(vault_root)
    record(vault_root, extras=["--wrong-questions", ""])
    result = run("analyze_paper.py", [str(vault_root), "--subject", "数学一"])
    assert result["papers"][0]["topic_wrong_counts"] == {}
    rc, out, _ = run_script("analyze_paper.py", [str(vault_root), "--subject", "数学一", "--start-date", DAY, "--end-date", "2026-10-01"])
    assert rc == 1 and json.loads(out)["error"]
