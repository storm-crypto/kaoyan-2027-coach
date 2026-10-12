"""卷面记录与卡片历史共同提供突破单证据，不能凭累计次数误触发。"""
import json
from datetime import date
from pathlib import Path

from helpers import run_script
from paper_wrong_questions import query_wrong_questions
from score_record_lib import collect_score_records


TODAY = "2026-10-12"


def record(root, paper, errors, topics=None, day=TODAY, subject="数学一"):
    args = [str(root), subject, "--paper", paper, "--paper-type", "真题", "--total", "100",
            "--issues", "多项失误", "--date", day, "--wrong-questions", errors]
    if topics is not None:
        args += ["--question-topics", topics]
    rc, out, err = run_script("record_paper_score.py", args)
    assert rc == 0, (out, err)
    return json.loads(out)


def check(root, days=3):
    rc, out, err = run_script("check_breakthrough_triggers.py",
                              [str(root), "--today", TODAY, "--days", str(days)])
    assert rc == 0, (out, err)
    return json.loads(out)


def card(root, qid, topic="二重积分", first=TODAY, history="", source="练习册"):
    path = root / "错题本" / "数学一" / "高等数学" / f"{qid}.md"
    path.write_text(f"---\nquestion_id: {qid}\ntopic: {topic}\nsource: {source}\n"
                    f"first_wrong_at: {first}\nwrong_count: 99\n---\n"
                    f"### 历史记录\n{history}", encoding="utf-8")
    return path


def test_one_paper_three_errors_trigger_and_query(sample_archive, vault_root):
    result = record(vault_root, "2010卷", "3:完全没思路;8:算错了;12:做到一半卡住",
                    "3:二重积分;8:二重积分;12:二重积分")
    records = collect_score_records(vault_root)
    errors = records[0]["wrong_questions"]
    assert len(errors) == 3
    assert errors[0] == {"question_number": 3, "error_description": "完全没思路",
                         "record_date": TODAY, "topic": "二重积分"}
    assert "## 卷子错题" in Path(result["record_path"]).read_text()
    found = query_wrong_questions(records, 8, date(2026, 10, 10), date(2026, 10, 12))
    assert len(found) == 1 and found[0]["error_description"] == "算错了"
    assert query_wrong_questions(records, start_date=date(2026, 10, 13)) == []
    assert check(vault_root)["triggered"] == [{"topic": "二重积分", "count": 3,
        "sources": ["2010卷第3题", "2010卷第8题", "2010卷第12题"], "subject": "数学一"}]


def test_cross_paper_and_date_window_do_not_trigger_two(sample_archive, vault_root):
    record(vault_root, "2010卷", "3:没思路;8:算错", "3:二重积分;8:二重积分", day="2026-10-10")
    assert check(vault_root)["triggered"] == []
    record(vault_root, "2011卷", "12:卡住", "12:二重积分", day="2026-10-11")
    record(vault_root, "旧卷", "1:不会;2:不会;3:不会", "1:泰勒;2:泰勒;3:泰勒", day="2026-10-09")
    record(vault_root, "未来卷", "1:不会;2:不会;3:不会", "1:泰勒;2:泰勒;3:泰勒", day="2026-10-13")
    assert [(t["topic"], t["count"]) for t in check(vault_root)["triggered"]] == [("二重积分", 3)]
    assert check(vault_root, days=1)["triggered"] == []


def test_generic_errors_stay_unmapped_and_keyword_uses_known_topics(sample_archive, vault_root):
    card(vault_root, "qid-000000000001", first="2026-01-01")
    record(vault_root, "2010卷", "3:没思路;8:算错;12:卡住")
    data = check(vault_root)
    assert data["triggered"] == [] and len(data["unmapped"]) == 3
    record(vault_root, "2010卷", "3:二重积分没思路;8:二重积分算错;12:二重积分卡住")
    assert check(vault_root)["triggered"][0]["count"] == 3


def test_card_history_counts_recent_failures_not_lifetime_or_success(vault_root):
    card(vault_root, "qid-000000000001", first="2026-01-01", history=
         "- 2026-10-10 - 不会 - 重错\n- 2026-10-11 - 半会 - 计算错\n"
         "- 2026-10-12 - 不会 - 重错\n- 2026-10-12 - 不会 - 重错\n")
    card(vault_root, "qid-000000000002", first="2026-01-01", history="- 2026-10-12 - 会 - 正确\n")
    trigger = check(vault_root)["triggered"][0]
    assert trigger["count"] == 3
    assert trigger["sources"] == ["qid-000000000001"] * 3


def test_distinct_failures_same_day_count_but_initial_and_retry_do_not(vault_root):
    card(vault_root, "qid-000000000001", history=
         f"- {TODAY} - 不会 - 首次归档\n"
         f"- {TODAY} - 半会 - 换序时出错\n"
         f"- {TODAY} - 半会 - 换序时出错\n"
         f"- {TODAY} - 不会 - 再测仍出错\n")
    assert check(vault_root)["triggered"][0]["count"] == 3


def test_paper_and_card_same_event_deduplicated(sample_archive, vault_root):
    record(vault_root, "2010卷", "3:算错;8:卡住", "3:二重积分;8:二重积分")
    card(vault_root, "qid-000000000001", source="2010卷第3题",
         history=f"- {TODAY} - 不会 - 首次\n")
    assert check(vault_root)["triggered"] == []
    card(vault_root, "qid-000000000002", history=f"- {TODAY} - 半会 - 首次\n")
    assert check(vault_root)["triggered"][0]["count"] == 3


def test_chapter_tags_and_subject_isolation(vault_root):
    for i in range(3):
        path = card(vault_root, f"qid-{i:012x}", topic="")
        path.write_text(path.read_text() + "\n#chapter/积分换序\n")
    assert check(vault_root)["triggered"][0]["topic"] == "积分换序"
    (vault_root / "错题本" / "英语一").mkdir()
    source = card(vault_root, "qid-000000000009", topic="积分换序")
    source.rename(vault_root / "错题本" / "英语一" / source.name)
    assert check(vault_root)["triggered"][0]["count"] == 3


def test_checker_rejects_invalid_window(vault_root):
    rc, out, _ = run_script("check_breakthrough_triggers.py", [str(vault_root), "--days", "0"])
    assert rc == 1 and json.loads(out)["error"]


def test_frontmatter_topic_tags_and_map_keyword_matching(sample_archive, vault_root):
    for i in range(3):
        path = card(vault_root, f"qid-{i:012x}", topic="")
        path.write_text(path.read_text().replace("topic: \n", "topic: \ntags: [topic/极坐标]\n"))
    (vault_root / "知识地图" / "数学一.md").write_text(
        "| 考点 | 掌握度 |\n|---|---|\n| 02.03 泰勒展开 | 半会 |\n")
    record(vault_root, "2010卷", "3:泰勒展开阶数不够;8:泰勒展开算错;12:泰勒展开没思路")
    assert [(t["topic"], t["count"]) for t in check(vault_root)["triggered"]] == [
        ("极坐标", 3), ("泰勒展开", 3)]
