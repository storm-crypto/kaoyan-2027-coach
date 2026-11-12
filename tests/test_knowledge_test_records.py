"""精确复验、无 qid 的证据闭环、同文件原子保存与重试语义。"""
import json
from datetime import date

import pytest

from helpers import run_script
from build_knowledge_test import parse_knowledge_map
from dashboard_payload import build_payload
from knowledge_map_parser import split_knowledge_row
from knowledge_test_records import identify_topics, read_test_records
from record_knowledge_test import record_knowledge_test
from workbench_payload import collect_knowledge
from workbench_view import render_workbench


def make_map(vault_root, *, topic="01.1 自定义考点", mastery="会", extra="", subject="政治"):
    path = vault_root / "知识地图" / f"{subject}.md"
    path.write_text(
        f"# {subject} 知识地图\n\n## 自定义模块\n\n"
        "| 考点 | 掌握度 | 信心 | 备注 |\n|---|---|---|---|\n"
        "| **01 自定义章节** | | | |\n"
        f"| {topic} | {mastery} | 高 | 保留原备注 |\n" + extra,
        encoding="utf-8",
    )
    rows = identify_topics(subject, parse_knowledge_map(path))
    return path, rows[0]["topic_id"]


def record(vault_root, topic_id, **changes):
    args = dict(topic_id=topic_id, test_id="test-one", question="说明判断依据并处理一个条件变化。",
                answer="独立指出了条件，并正确处理变式。", judgment="依据与变式均正确。",
                hinted=False, result="会", test_date="2026-11-11")
    args.update(changes)
    return record_knowledge_test(vault_root, "政治", **args)


def test_explicit_topic_retests_known_without_changing_default_selection(vault_root):
    path, topic_id = make_map(vault_root, extra="| 01.2 另一弱项 | 不会 | | |\n")
    rc, out, err = run_script("build_knowledge_test.py", [str(vault_root), "政治"])
    assert rc == 0, err
    default = json.loads(out)
    assert [q["topic"] for q in default["questions"]] == ["01.2 另一弱项"]
    assert default["questions"][0]["topic_id"] and default["questions"][0]["test_id"]

    rc, out, err = run_script("build_knowledge_test.py", [str(vault_root), "政治", "--topic-id", topic_id])
    assert rc == 0, err
    exact = json.loads(out)
    assert exact["question_count"] == 1
    assert exact["questions"][0]["topic_id"] == topic_id
    assert exact["questions"][0]["source_mastery"] == "会"
    assert identify_topics("政治", parse_knowledge_map(path))[0]["topic_id"] == topic_id


def test_chapter_scope_does_not_retest_all_known_topics(vault_root):
    make_map(vault_root)
    rc, out, _ = run_script("build_knowledge_test.py", [str(vault_root), "政治", "--chapter", "自定义模块"])
    assert rc == 1
    assert json.loads(out)["error"]


def test_duplicate_exact_topic_rejected_without_writing(vault_root):
    path, topic_id = make_map(vault_root, extra="| 01.1 自定义考点 | 半会 | | |\n")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="匹配 2 行"):
        record(vault_root, topic_id)
    rc, out, _ = run_script("build_knowledge_test.py", [str(vault_root), "政治", "--topic-id", topic_id])
    assert rc == 1 and "匹配 2 行" in json.loads(out)["message"]
    assert path.read_bytes() == before


def test_same_named_legacy_topics_in_different_modules_have_distinct_ids(vault_root):
    path, _ = make_map(vault_root, extra="\n## 另一个模块\n| 考点 | 掌握度 | 信心 | 备注 |\n| 01.1 自定义考点 | 会 | | |\n")
    rows = identify_topics("政治", parse_knowledge_map(path))
    assert len({row["topic_id"] for row in rows}) == 2


def test_prompted_pass_is_rejected_but_partial_result_records_evidence(vault_root):
    path, topic_id = make_map(vault_root)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="最多记半会"):
        record(vault_root, topic_id, hinted=True)
    assert path.read_bytes() == before
    saved = record(vault_root, topic_id, hinted=True, result="半会")
    assert saved["mastery"] == "半会"
    assert parse_knowledge_map(path)[0]["mastery"] == "半会"
    assert parse_knowledge_map(path)[0]["note"] == "保留原备注"
    assert read_test_records(path.read_text())[0]["hinted"] is True
    assert not list((vault_root / "错题本").rglob("*.md"))


def test_record_replay_is_idempotent_and_cannot_replace_another_answer(vault_root):
    path, topic_id = make_map(vault_root)
    record(vault_root, topic_id)
    record(vault_root, topic_id, test_id="test-two", result="不会", test_date="2026-11-12")
    before = path.read_bytes()
    replay = record(vault_root, topic_id)
    assert replay["replayed"] and replay["mastery"] == "不会"
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="已用于不同作答"):
        record(vault_root, topic_id, answer="这次换了答案")
    assert path.read_bytes() == before
    assert len(read_test_records(path.read_text())) == 2


def test_earlier_backfill_preserves_newer_mastery(vault_root):
    path, topic_id = make_map(vault_root)
    record(vault_root, topic_id, result="半会")
    saved = record(vault_root, topic_id, test_id="test-older", result="会", test_date="2026-11-10")
    assert saved["mastery_updated"] is False
    assert parse_knowledge_map(path)[0]["mastery"] == "半会"
    assert len(read_test_records(path.read_text())) == 2


def test_atomic_write_receives_mastery_and_evidence_together(vault_root, monkeypatch):
    path, topic_id = make_map(vault_root)
    before = path.read_bytes()
    received = []

    def fail_write(target, content):
        received.append((target, content))
        raise OSError("模拟写入中断")

    monkeypatch.setattr("record_knowledge_test.atomic_write", fail_write)
    with pytest.raises(OSError, match="模拟写入中断"):
        record(vault_root, topic_id, result="不会")
    assert len(received) == 1
    assert parse_knowledge_map(path, text=received[0][1])[0]["mastery"] == "不会"
    assert read_test_records(received[0][1])[0]["result"] == "不会"
    assert path.read_bytes() == before


def test_corrupt_record_refuses_overwrite_and_workbench_reports_it(vault_root):
    path, topic_id = make_map(vault_root)
    record(vault_root, topic_id)
    path.write_text(path.read_text().replace('"hinted": false', '"hinted": "false"'))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="记录损坏"):
        record(vault_root, topic_id, test_id="test-two")
    assert path.read_bytes() == before
    data = next(item for item in collect_knowledge(vault_root, []) if item["subject"] == "政治")
    assert data["warnings"] and data["chapters"][0]["topics"][0]["tests"] == []


def test_cli_to_workbench_no_qid_round_trip_preserves_question_and_conditions(vault_root):
    path, topic_id = make_map(vault_root, mastery="不会")
    question = "若 $|x| < 1$，如何判断？\n请补充变式。"
    rc, out, err = run_script("record_knowledge_test.py", [
        str(vault_root), "政治", "--topic-id", topic_id, "--test-id", "test-cli",
        "--question", question, "--answer", "<script>内容应作为文本</script>",
        "--judgment", "结论正确且能解释变式", "--hinted", "no", "--result", "会",
        "--today", "2026-11-11",
    ])
    assert rc == 0, err + out
    assert json.loads(out)["mastery_updated"]
    assert len(parse_knowledge_map(path)) == 1
    assert read_test_records(path.read_text())[0]["question"] == question
    payload = build_payload(vault_root, date(2026, 11, 11))
    topic = next(s for s in payload["workbench"]["knowledge"] if s["subject"] == "政治")["chapters"][0]["topics"][0]
    assert topic["tests"][0]["result"] == "会" and topic["evidence"] == []
    assert topic["command"] == f"/test 政治 --topic-id {topic_id}"
    html = render_workbench(payload, "statistics.html")
    assert "知识测试 · 2026-11-11 · 无提示作答 · 会" in html
    assert "<script>内容应作为文本</script>" not in html
    assert "&lt;script&gt;内容应作为文本&lt;/script&gt;" in html


def test_escaped_pipe_topic_survives_build_record_update_and_workbench(vault_root):
    topic = r"01.03 第三节 讨论 \|A\|=0 的问题"
    path, topic_id = make_map(vault_root, topic=topic, subject="数学一")
    assert split_knowledge_row(f"| {topic} | 会 | | 备注 |") == [topic, "会", "", "备注"]
    rc, out, err = run_script("build_knowledge_test.py", [str(vault_root), "数学一", "--topic-id", topic_id])
    assert rc == 0, err + out
    assert json.loads(out)["questions"][0]["topic"] == topic
    record_knowledge_test(vault_root, "数学一", topic_id=topic_id, test_id="test-determinant",
                          question="讨论行列式为零的情形。", answer="需要提示。", judgment="提示后会完成",
                          hinted=True, result="半会", test_date="2026-11-11")
    assert parse_knowledge_map(path)[0]["topic"] == topic
    rc, out, err = run_script("update_knowledge_map.py", [str(vault_root), "数学一", topic, "不会"])
    assert rc == 0, err + out
    payload = build_payload(vault_root, date(2026, 11, 11))
    item = next(s for s in payload["workbench"]["knowledge"] if s["subject"] == "数学一")["chapters"][0]["topics"][0]
    assert item["name"] == topic and item["status"] == "不会"
    assert item["tests"][0]["result"] == "半会"


def test_readable_evidence_preserves_latex_and_escapes_html(vault_root):
    path, topic_id = make_map(vault_root)
    question = "若 $|x| < 1$，验证\n$$\nf'(x) > 0\n$$\n<script>仅文字</script>"
    record(vault_root, topic_id, question=question)
    text = path.read_text()
    assert "> 若 $|x| < 1$，验证" in text
    assert "> f'(x) > 0" in text
    assert "> &lt;script&gt;仅文字&lt;/script&gt;" in text
    assert read_test_records(text)[0]["question"] == question
