"""test knowledge_findings.py"""
import sys
import textwrap
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from knowledge_findings import (
    DEFAULT_FOLD_THRESHOLD,
    Finding,
    merge_findings,
    parse_findings,
    render_findings,
    sync_mastered_status,
)


# ---- parse_findings ----

def test_parse_single_unmastered_finding():
    cell = "1. [2026-04-15] 参数极限题先保阶再定常数没固化 (qid-bbbb22223333)"
    findings, legacy = parse_findings(cell)
    assert legacy == ""
    assert len(findings) == 1
    assert findings[0].qid == "qid-bbbb22223333"
    assert findings[0].first_exposed == date(2026, 4, 15)
    assert findings[0].description == "参数极限题先保阶再定常数没固化"
    assert findings[0].mastered_at is None
    assert findings[0].source == "wrong_card"


def test_parse_strikethrough_mastered_finding():
    cell = "1. ~~[2026-04-01 → 2026-05-01] 左右极限触发器不稳 (qid-aaaa11112222)~~"
    findings, legacy = parse_findings(cell)
    assert legacy == ""
    assert len(findings) == 1
    assert findings[0].mastered_at == date(2026, 5, 1)
    assert findings[0].first_exposed == date(2026, 4, 1)
    assert findings[0].description == "左右极限触发器不稳"


def test_parse_multiline_br_separated():
    cell = (
        "1. [2026-04-15] 参数极限不稳 (qid-bbbb22223333)<br>"
        "2. [2026-05-10] 积分型无穷小比较 (qid-cccc33334444)"
    )
    findings, legacy = parse_findings(cell)
    assert legacy == ""
    assert len(findings) == 2
    assert findings[0].qid == "qid-bbbb22223333"
    assert findings[1].qid == "qid-cccc33334444"


def test_parse_details_block_extracts_inner_findings():
    cell = (
        "1. [2026-05-10] 未掌握A (qid-1111aaaa1111)<br>"
        "<details><summary>已掌握 2 条</summary>"
        "2. ~~[2026-04-01 → 2026-05-01] 旧A (qid-aaaa11112222)~~<br>"
        "3. ~~[2026-04-03 → 2026-05-03] 旧B (qid-dddd44445555)~~"
        "</details>"
    )
    findings, legacy = parse_findings(cell)
    assert legacy == ""
    assert len(findings) == 3
    mastered_qids = {f.qid for f in findings if f.mastered_at}
    assert mastered_qids == {"qid-aaaa11112222", "qid-dddd44445555"}


def test_parse_legacy_free_text_goes_to_legacy():
    cell = "左右极限不稳，参数极限也不稳，积分型无穷小比较还得练"
    findings, legacy = parse_findings(cell)
    assert findings == []
    assert "左右极限不稳" in legacy


def test_parse_grill_qid_recognized_as_grill_source():
    cell = "1. [2026-05-10] 章节诊断条目 (qid-grill-1234567890)"
    findings, legacy = parse_findings(cell)
    assert len(findings) == 1
    assert findings[0].source == "grill"


def test_parse_mixed_findings_and_legacy_separated():
    cell = (
        "1. [2026-04-15] 真 finding (qid-bbbb22223333)<br>"
        "这是一段乱写的老备注"
    )
    findings, legacy = parse_findings(cell)
    assert len(findings) == 1
    assert findings[0].qid == "qid-bbbb22223333"
    assert "乱写的老备注" in legacy


# ---- merge_findings ----

def test_merge_appends_new_qid():
    existing: list[Finding] = []
    result = merge_findings(existing, "qid-aaaa11112222", date(2026, 5, 10), "新卡点")
    assert len(result) == 1
    assert result[0].qid == "qid-aaaa11112222"
    assert result[0].description == "新卡点"
    assert result[0].mastered_at is None


def test_merge_updates_description_for_existing_qid():
    existing = [
        Finding(qid="qid-aaaa11112222", first_exposed=date(2026, 4, 1), description="旧描述"),
    ]
    result = merge_findings(existing, "qid-aaaa11112222", date(2026, 5, 10), "新描述更精确")
    assert len(result) == 1
    assert result[0].description == "新描述更精确"
    # first_exposed 不变
    assert result[0].first_exposed == date(2026, 4, 1)


def test_merge_truncates_overlong_description():
    long_desc = "x" * 100
    result = merge_findings([], "qid-aaaa11112222", date(2026, 5, 10), long_desc)
    assert len(result[0].description) <= 40
    assert result[0].description.endswith("…")


# ---- render_findings ----

def test_render_empty_returns_empty():
    assert render_findings([]) == ""


def test_render_unmastered_only():
    findings = [
        Finding(qid="qid-bbbb22223333", first_exposed=date(2026, 4, 15), description="参数极限"),
        Finding(qid="qid-cccc33334444", first_exposed=date(2026, 5, 10), description="积分型无穷小"),
    ]
    rendered = render_findings(findings)
    assert rendered.startswith("1. [2026-04-15]")
    assert "2. [2026-05-10]" in rendered
    assert "<br>" in rendered
    assert "<details>" not in rendered
    assert "~~" not in rendered


def test_render_mastered_strikethrough_and_arrow():
    findings = [
        Finding(
            qid="qid-aaaa11112222",
            first_exposed=date(2026, 4, 1),
            description="左右极限",
            mastered_at=date(2026, 5, 1),
        ),
    ]
    rendered = render_findings(findings)
    assert "~~[2026-04-01 → 2026-05-01] 左右极限 (qid-aaaa11112222)~~" in rendered


def test_render_unmastered_before_mastered():
    findings = [
        Finding(
            qid="qid-aaaa11112222",
            first_exposed=date(2026, 4, 1),
            description="老A",
            mastered_at=date(2026, 5, 1),
        ),
        Finding(qid="qid-bbbb22223333", first_exposed=date(2026, 4, 15), description="新B"),
    ]
    rendered = render_findings(findings)
    new_pos = rendered.find("新B")
    old_pos = rendered.find("老A")
    assert 0 <= new_pos < old_pos


def test_render_folds_when_mastered_meets_threshold():
    findings = [
        Finding(qid="qid-aa11aa11aa11", first_exposed=date(2026, 4, 1), description="A", mastered_at=date(2026, 5, 1)),
        Finding(qid="qid-bb22bb22bb22", first_exposed=date(2026, 4, 2), description="B", mastered_at=date(2026, 5, 2)),
        Finding(qid="qid-cc33cc33cc33", first_exposed=date(2026, 4, 3), description="C", mastered_at=date(2026, 5, 3)),
    ]
    rendered = render_findings(findings, fold_threshold=3)
    assert "<details><summary>已掌握 3 条</summary>" in rendered
    assert "</details>" in rendered


def test_render_no_fold_below_threshold():
    findings = [
        Finding(qid="qid-aa11aa11aa11", first_exposed=date(2026, 4, 1), description="A", mastered_at=date(2026, 5, 1)),
        Finding(qid="qid-bb22bb22bb22", first_exposed=date(2026, 4, 2), description="B", mastered_at=date(2026, 5, 2)),
    ]
    rendered = render_findings(findings, fold_threshold=3)
    assert "<details>" not in rendered
    assert "~~" in rendered


def test_render_tombstone_does_not_pollute_visual():
    """tombstone 字段保留在数据里供诊断用，但渲染时不加视觉前缀以免干扰正常输出。"""
    findings = [
        Finding(
            qid="qid-aaaa11112222",
            first_exposed=date(2026, 4, 1),
            description="找不到对应卡",
            tombstone=True,
        ),
    ]
    rendered = render_findings(findings)
    assert "⚠" not in rendered
    assert "找不到对应卡" in rendered


# ---- parse + render 往返 ----

def test_parse_render_roundtrip():
    findings = [
        Finding(
            qid="qid-aaaa11112222",
            first_exposed=date(2026, 4, 1),
            description="左右极限",
            mastered_at=date(2026, 5, 1),
        ),
        Finding(qid="qid-bbbb22223333", first_exposed=date(2026, 4, 15), description="参数极限"),
    ]
    cell = render_findings(findings)
    parsed, legacy = parse_findings(cell)
    assert legacy == ""
    assert len(parsed) == 2
    qid_to_finding = {f.qid: f for f in parsed}
    assert qid_to_finding["qid-aaaa11112222"].mastered_at == date(2026, 5, 1)
    assert qid_to_finding["qid-bbbb22223333"].mastered_at is None


# ---- sync_mastered_status ----

def _make_card(vault_root, qid, interval, last_review):
    card_dir = vault_root / "错题本" / "数学一" / "高等数学"
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / f"test-{qid}.md"
    card.write_text(textwrap.dedent(f"""\
        ---
        source: 测试
        question_id: {qid}
        topic: 测试
        error_tags: []
        first_wrong_at: 2026-04-01
        last_review_at: {last_review}
        wrong_count: 1
        status: 不会
        next_review: 2026-05-15
        review_interval: {interval}
        ease_factor: 2.50
        ---

        #subject/math1

        ## 测试
    """), encoding="utf-8")
    return card


def test_sync_marks_mastered_when_interval_meets_threshold(vault_root):
    _make_card(vault_root, "qid-aaaa11112222", interval=15, last_review="2026-05-10")
    findings = [Finding(qid="qid-aaaa11112222", first_exposed=date(2026, 4, 1), description="A")]
    synced = sync_mastered_status(findings, Path(vault_root), threshold_days=14)
    assert synced[0].mastered_at == date(2026, 5, 10)


def test_sync_skips_below_threshold(vault_root):
    _make_card(vault_root, "qid-bbbb22223333", interval=10, last_review="2026-05-10")
    findings = [Finding(qid="qid-bbbb22223333", first_exposed=date(2026, 4, 1), description="B")]
    synced = sync_mastered_status(findings, Path(vault_root), threshold_days=14)
    assert synced[0].mastered_at is None
    assert synced[0].tombstone is False


def test_sync_marks_tombstone_when_card_missing(vault_root):
    findings = [Finding(qid="qid-zzzz99998888", first_exposed=date(2026, 4, 1), description="找不到")]
    synced = sync_mastered_status(findings, Path(vault_root), threshold_days=14)
    assert synced[0].tombstone is True
    assert synced[0].mastered_at is None


def test_sync_skips_grill_source(vault_root):
    findings = [
        Finding(
            qid="qid-grill-1234567890",
            first_exposed=date(2026, 4, 1),
            description="章节诊断",
            source="grill",
        ),
    ]
    synced = sync_mastered_status(findings, Path(vault_root), threshold_days=14)
    assert synced[0].tombstone is False
    assert synced[0].mastered_at is None


def test_sync_preserves_already_mastered(vault_root):
    _make_card(vault_root, "qid-aaaa11112222", interval=20, last_review="2026-06-01")
    findings = [
        Finding(
            qid="qid-aaaa11112222",
            first_exposed=date(2026, 4, 1),
            description="A",
            mastered_at=date(2026, 5, 1),  # 已经标过了
        ),
    ]
    synced = sync_mastered_status(findings, Path(vault_root), threshold_days=14)
    # 不会被 sync 覆盖掉
    assert synced[0].mastered_at == date(2026, 5, 1)
