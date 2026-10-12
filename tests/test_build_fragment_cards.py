import json

import pytest

from helpers import run_script


DAY = "2026-10-12"


def card(root, number=1, interval=1, due=DAY, question=None):
    qid = f"qid-{number:012x}"
    path = root / "错题本" / "数学一" / "高等数学" / f"card-{qid}.md"
    question = question if question is not None else (
        f"### 题目\n第{number}道题：求 $f'(x)$。\n![[错题本/_附图/{qid}/题图.svg]]\n"
        "A. 1\nB. 2\n")
    path.write_text(f"---\nquestion_id: {qid}\ntopic: 积分\nnext_review: {due}\n"
                    f"review_interval: {interval}\n---\n{question}\n"
                    "### 规范解法\n解析：秘密答案\n### 历史记录\n- 不应出现\n")
    return path, qid


def build(root, count=5):
    rc, out, err = run_script("build_fragment_cards.py", [str(root), "--date", DAY, "--count", str(count)])
    assert rc == 0, (out, err)
    return json.loads(out), root / "碎片刷题" / f"{DAY}.md"


def test_fragment_contains_only_question_and_qid_and_preserves_cards(vault_root):
    source, qid = card(vault_root)
    original = source.read_bytes()
    data, path = build(vault_root)
    text = path.read_text()
    assert data["qids"] == [qid] and data["count"] == 1
    assert "$f'(x)$" in text and "![[错题本/_附图/" in text and "B. 2" in text
    assert all(secret not in text for secret in ("解析", "秘密答案", "规范解法", "历史记录"))
    assert source.read_bytes() == original


def test_plan_cluster_priority_then_srs_urgency(vault_root):
    _, urgent = card(vault_root, 1, interval=1)
    _, preferred = card(vault_root, 2, interval=14)
    _, older = card(vault_root, 3, interval=1, due="2026-10-10")
    card(vault_root, 4, due="2026-10-13")
    card(vault_root, 5, interval=90)
    (vault_root / "错题本" / "_元技能索引.json").write_text(json.dumps({"clusters": [
        {"id": "integral", "skill": "画域换序", "ch": "积分", "qids": [preferred[4:]]}]}))
    (vault_root / "周计划" / "_今日计划.md").write_text(
        f"# 今日计划：{DAY}\n## 任务清单\n- [ ] [数学一] 复习画域换序簇\n")
    data, _ = build(vault_root, 3)
    assert data["qids"] == [preferred, older, urgent]


def test_stale_plan_does_not_prioritize(vault_root):
    _, urgent = card(vault_root, 1, interval=1)
    _, other = card(vault_root, 2, interval=14)
    (vault_root / "周计划" / "_今日计划.md").write_text(
        f"# 今日计划：2026-10-11\n## 任务清单\n- [ ] [数学一] 复习 {other}\n")
    assert build(vault_root, 1)[0]["qids"] == [urgent]


def test_fragment_idempotent_does_not_overwrite_user_or_reselect(vault_root):
    card(vault_root)
    _, path = build(vault_root)
    path.write_text(path.read_text() + "\n手机上已做\n")
    original, mtime = path.read_bytes(), path.stat().st_mtime_ns
    card(vault_root, 2)
    data, _ = build(vault_root, 2)
    assert data["created"] is False and data["count"] == 1
    assert path.read_bytes() == original and path.stat().st_mtime_ns == mtime


def test_no_due_cards_creates_truly_empty_file_and_json_hint(vault_root):
    card(vault_root, due="2026-10-13")
    data, path = build(vault_root)
    assert data["count"] == 0 and "没有到期卡" in data["message"]
    assert path.read_bytes() == b""
    assert build(vault_root)[0]["created"] is False


def test_missing_question_is_skipped_instead_of_using_solution(vault_root):
    card(vault_root, question="### 错误原因\n不能当题面\n")
    data, path = build(vault_root)
    assert data["count"] == 0 and data["skipped"] and path.read_bytes() == b""


@pytest.mark.parametrize("next_heading", ["## 解析", "# 解析", "### 解析"])
def test_higher_heading_stops_question_extraction(vault_root, next_heading):
    card(vault_root, question=f"### 题目\n题面正文\n{next_heading}\n不能泄露的解答\n")
    _, path = build(vault_root)
    assert "题面正文" in path.read_text()
    assert "解析" not in path.read_text() and "不能泄露" not in path.read_text()


def test_fenced_heading_remains_question_content(vault_root):
    card(vault_root, question="### 题目\n阅读代码：\n```python\n# 一个注释\n```\n求输出。\n")
    _, path = build(vault_root)
    assert "# 一个注释" in path.read_text() and "求输出。" in path.read_text()
    assert "秘密答案" not in path.read_text()


def test_unclosed_question_fence_cannot_swallow_solution(vault_root):
    card(vault_root, question="### 题目\n```python\n求输出\n")
    data, path = build(vault_root)
    assert data["count"] == 0 and data["skipped"]
    assert path.read_bytes() == b""


def test_frontmatter_qid_works_without_qid_filename(vault_root):
    path, qid = card(vault_root)
    path.rename(path.with_name("题卡.md"))
    assert build(vault_root)[0]["qids"] == [qid]


def test_invalid_count_is_json_error(vault_root):
    rc, out, _ = run_script("build_fragment_cards.py", [str(vault_root), "--count", "0"])
    assert rc == 1 and json.loads(out)["error"]
    assert not (vault_root / "碎片刷题").exists()
