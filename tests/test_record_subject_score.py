"""test record_subject_score.py"""
import json
import textwrap

from helpers import run_script


def test_record_math_subject_score(sample_archive, vault_root):
    rc, out, _ = run_script("record_subject_score.py", [
        str(vault_root),
        "数学一",
        "--date", "2026-03-24",
        "--paper", "李林6套卷3",
        "--score", "122",
        "--issues", "极值与驻点定义、幂级数敛散",
        "--note", "基础盘稳了不少",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["subject"] == "数学一"
    archive_text = sample_archive.read_text(encoding="utf-8")
    assert "| 2026-03-24 | 模拟 | 李林6套卷3 | 122 | 极值与驻点定义、幂级数敛散 | 基础盘稳了不少 |" in archive_text
    assert (vault_root / "成绩记录" / "数学一" / "2026-03-24-模拟-李林6套卷3.md").exists()


def test_record_408_subject_score_same_day_upsert(sample_archive, vault_root):
    run_script("record_subject_score.py", [
        str(vault_root),
        "408",
        "--date", "2026-03-24",
        "--paper", "2024 真题",
        "--ds", "2",
        "--co", "1",
        "--os", "4",
        "--cn", "2",
        "--total", "118",
        "--issues", "OS 调度、CO 指令系统",
        "--note", "初版",
    ])

    rc, out, _ = run_script("record_subject_score.py", [
        str(vault_root),
        "408",
        "--date", "2026-03-24",
        "--paper", "2024 真题",
        "--ds", "1",
        "--co", "1",
        "--os", "3",
        "--cn", "2",
        "--total", "123",
        "--issues", "OS 调度、CN 拥塞控制",
        "--note", "修正版",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["subject"] == "408"
    archive_text = sample_archive.read_text(encoding="utf-8")
    assert archive_text.count("| 2026-03-24 | 真题 | 2024 真题 |") == 1
    assert "| 2026-03-24 | 真题 | 2024 真题 | 123 | OS 调度、CN 拥塞控制 | 修正版 |" in archive_text
    assert (vault_root / "成绩记录" / "408" / "2026-03-24-真题-2024-真题.md").exists()


def test_record_subject_score_bootstraps_missing_sections(vault_root):
    archive = vault_root / "我的学习者档案.md"
    archive.write_text(textwrap.dedent("""\
        # 我的学习者档案

        ## 基本信息
        - **最近更新日期**：2026-03-20

        ## 模考成绩追踪
        | 日期 | 政治 | 数学一 | 英语一 | 408 | 总分 | 备注 |
        |------|------|--------|--------|-----|------|------|
        | 初始 | | | | | | 基准分 |

        ## 最近聚焦问题（只保留 3-5 条）
        - 数学推进
    """), encoding="utf-8")

    rc, out, _ = run_script("record_subject_score.py", [
        str(vault_root),
        "数学",
        "--date", "2026-03-24",
        "--paper", "2024 真题二刷",
        "--score", "130",
        "--issues", "二次型不等式、二重积分换序",
        "--note", "真题二刷能看出基础回来了",
    ])

    assert rc == 0
    content = archive.read_text(encoding="utf-8")
    assert "## 数学一模拟成绩追踪" in content
    assert "## 408模拟成绩追踪" in content
    assert "## 英语一模拟成绩追踪" in content
    assert "| 2026-03-24 | 真题 | 2024 真题二刷 | 130 | 二次型不等式、二重积分换序 | 真题二刷能看出基础回来了 |" in content
