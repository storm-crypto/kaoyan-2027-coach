"""test generate_question_id.py"""
import json
from helpers import run_script


def test_normal_output():
    rc, out, _ = run_script("generate_question_id.py", ["900题", "第12题 二重积分"])
    assert rc == 0
    data = json.loads(out)
    assert data["question_id"].startswith("qid-")
    assert len(data["question_id"]) == 16  # qid- + 12 hex


def test_idempotent():
    _, out1, _ = run_script("generate_question_id.py", ["900题", "第12题 二重积分"])
    _, out2, _ = run_script("generate_question_id.py", ["900题", "第12题 二重积分"])
    assert json.loads(out1)["question_id"] == json.loads(out2)["question_id"]


def test_unicode_normalization():
    """全角数字和半角数字应生成相同 qid。"""
    _, out1, _ = run_script("generate_question_id.py", ["900题", "第12题"])
    _, out2, _ = run_script("generate_question_id.py", ["９００题", "第１２题"])  # 全角
    assert json.loads(out1)["question_id"] == json.loads(out2)["question_id"]


def test_missing_args():
    rc, out, _ = run_script("generate_question_id.py", [])
    assert rc == 1
    assert json.loads(out)["error"] is True


def test_empty_source():
    rc, out, _ = run_script("generate_question_id.py", ["!!!", "第12题"])
    assert rc == 1
    assert json.loads(out)["error"] is True
