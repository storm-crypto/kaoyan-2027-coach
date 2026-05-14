"""test import_chapter_grill.py"""
import json
import textwrap

from helpers import run_script


def _write_408_knowledge_map(vault_root):
    content = textwrap.dedent("""\
        ## 数据结构 (约 45 分)
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **01 线性表** | | | |
        |   01.1 顺序表 | | | |

        ## 计算机组成原理 (约 45 分)
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **01 计算机系统概述** | | | |
        |   01.1 计算机发展与层次结构 | | | |
        |   01.2 性能指标（CPI/MIPS/主频） | | | |
        | **03 存储系统** | | | |
        |   03.2 Cache（映射方式/替换策略/写策略） | | | |
        | **06 总线** | | | |
        |   06.1 总线概述与分类 | | | |
        |   06.2 总线仲裁与定时 | | | |
    """)
    path = vault_root / "知识地图" / "408.md"
    path.write_text(content, encoding="utf-8")
    return path


def _write_voyager_json(tmp_path, payload):
    path = tmp_path / "voyager.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _structured_assistant_text():
    return textwrap.dedent("""\
        这章整体是半会。你能复述性能指标，但执行时间的因果链还没讲透。

        【章节信息】
        - 科目：408
        - 模块：计算机组成原理
        - 章节：01 计算机系统概述
        - 资料来源：老汤讲408 PPT

        【本章结论】
        - 总体掌握：半会
        - 一句话结论：能背公式，但还没把 CPU 时间、CPI 和主频之间的关系讲顺。

        【已掌握】
        - 计算机层次结构的基本划分已经能讲清

        【半会但不稳】
        - 性能指标（CPI/MIPS/主频）的推理链条还不稳

        【不会或有能力错觉】
        - Cache（映射方式/替换策略/写策略）只能背概念，讲不出冲突缺失根源

        【关键漏洞】
        - 把 CPI 和执行时间关系说反
        - 讲指标时只报术语，没有落到状态变化

        【下一步复习动作】
        - 24小时内：重讲一次 CPU 执行时间公式
        - 3天内：补两道性能指标变式题
        - 下次开始前：先脱稿复述性能指标和 Cache 的判断轴

        【可映射考点】
        - 性能指标（CPI/MIPS/主频）|半会|把 CPI 和执行时间关系说反
        - Cache（映射方式/替换策略/写策略）|不会|只能背概念，讲不出冲突缺失根源
    """)


def test_import_chapter_grill_success(vault_root, tmp_path):
    knowledge_map_path = _write_408_knowledge_map(vault_root)
    payload = {
        "format": "gemini-voyager.chat.v1",
        "url": "https://gemini.google.com/app/test",
        "exportedAt": "2026-04-10T02:41:32.818Z",
        "count": 1,
        "title": "Gemini 辅助 408 复盘与知识库构建",
        "items": [{
            "user": "我们来复盘计组第一章。",
            "assistant": textwrap.dedent("""\
                【判卷结论】
                你能复述指标定义，但执行时间的因果链还没讲透。

                【漏洞定位】
                1. 术语糊弄：只背了 CPI、主频、MIPS 的字面定义。
                2. 逻辑断层：没把执行时间和时钟周期数连起来。

                【纠偏方向】
                先把 CPU 执行时间公式讲顺，再谈指标对比。

                【追问】
                如果 CPI 上升而主频不变，执行时间为什么会变长？
            """),
        }, {
            "user": "结束本章，按模板总评",
            "assistant": _structured_assistant_text(),
        }],
    }
    voyager_path = _write_voyager_json(tmp_path, payload)

    rc, out, _ = run_script("import_chapter_grill.py", [
        str(vault_root), str(voyager_path)
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["import_confidence"] == "high"
    assert data["module"] == "计算机组成原理"
    assert data["chapter"] == "01 计算机系统概述"
    report_path = vault_root / "章节掌握报告" / "408" / "计算机组成原理" / "2026-04-10-01-计算机系统概述.md"
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "type: chapter_grill_report" in content
    assert "## 本章结论" in content
    assert "## 知识地图回写结果" in content
    km_content = knowledge_map_path.read_text(encoding="utf-8")
    assert "性能指标（CPI/MIPS/主频） | 半会 |" in km_content
    assert "Cache（映射方式/替换策略/写策略） | 不会 |" in km_content
    # 章节拷打的备注应该以 Finding 格式落盘（qid-grill-xxxxxxxxxx 主键）
    perf_line = next(line for line in km_content.splitlines() if "性能指标（CPI/MIPS/主频）" in line and "|" in line)
    assert "(qid-grill-" in perf_line
    assert "1. [" in perf_line
    assert "把 CPI 和执行时间关系说反" in perf_line


def test_import_chapter_grill_rejects_invalid_format(vault_root, tmp_path):
    voyager_path = _write_voyager_json(tmp_path, {
        "format": "other-format",
        "items": [{"user": "a", "assistant": "b"}],
    })

    rc, out, _ = run_script("import_chapter_grill.py", [
        str(vault_root), str(voyager_path)
    ])

    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True


def test_import_chapter_grill_fallback_mode(vault_root, tmp_path):
    _write_408_knowledge_map(vault_root)
    payload = {
        "format": "gemini-voyager.chat.v1",
        "exportedAt": "2026-04-11T02:41:32.818Z",
        "count": 1,
        "title": "复盘计算机组成原理",
        "items": [{
            "user": "我们继续复盘计算机组成原理第一章。",
            "assistant": textwrap.dedent("""\
                【判卷结论】
                这章整体只能算半会。

                【漏洞定位】
                1. 术语糊弄：性能指标只会背定义。
                2. 逻辑断层：CPU 时间的因果链没有讲顺。

                【追问】
                如果主频不变，为什么 CPI 变大会拉长执行时间？
            """),
        }],
    }
    voyager_path = _write_voyager_json(tmp_path, payload)

    rc, out, _ = run_script("import_chapter_grill.py", [
        str(vault_root), str(voyager_path)
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["import_confidence"] == "low"
    report_path = vault_root / "章节掌握报告" / "408" / "计算机组成原理" / "2026-04-11-第1章.md"
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "未检测到固定总评块" in content


def test_import_chapter_grill_skips_unmatched_and_ambiguous_topics(vault_root, tmp_path):
    _write_408_knowledge_map(vault_root)
    payload = {
        "format": "gemini-voyager.chat.v1",
        "exportedAt": "2026-04-12T02:41:32.818Z",
        "count": 1,
        "title": "Gemini 辅助 408 复盘与知识库构建",
        "items": [{
            "user": "结束本章，按模板总评",
            "assistant": textwrap.dedent("""\
                【章节信息】
                - 科目：408
                - 模块：计算机组成原理
                - 章节：06 总线
                - 资料来源：老汤讲408 PPT

                【本章结论】
                - 总体掌握：半会
                - 一句话结论：总线部分概念有印象，但判断轴不稳。

                【已掌握】
                - 暂无

                【半会但不稳】
                - 总线仲裁

                【不会或有能力错觉】
                - 总线

                【关键漏洞】
                - 题干一变就会混

                【下一步复习动作】
                - 24小时内：回看总线基础
                - 3天内：做两道总线题
                - 下次开始前：先讲清总线仲裁方式

                【可映射考点】
                - 总线|半会|关键词太宽，应该触发多义跳过
                - 不存在考点|不会|知识地图里没有这一项
            """),
        }],
    }
    voyager_path = _write_voyager_json(tmp_path, payload)

    rc, out, _ = run_script("import_chapter_grill.py", [
        str(vault_root), str(voyager_path)
    ])

    assert rc == 0
    data = json.loads(out)
    assert len(data["knowledge_map_updated"]) == 0
    assert len(data["knowledge_map_skipped"]) == 2
    reasons = {item["topic"]: item["reason"] for item in data["knowledge_map_skipped"]}
    assert "多行候选" in reasons["总线"]
    assert "未找到匹配" in reasons["不存在考点"]


def test_import_chapter_grill_uses_incrementing_suffix(vault_root, tmp_path):
    _write_408_knowledge_map(vault_root)
    payload = {
        "format": "gemini-voyager.chat.v1",
        "exportedAt": "2026-04-10T02:41:32.818Z",
        "count": 1,
        "title": "Gemini 辅助 408 复盘与知识库构建",
        "items": [{
            "user": "结束本章，按模板总评",
            "assistant": _structured_assistant_text(),
        }],
    }
    voyager_path = _write_voyager_json(tmp_path, payload)

    rc1, out1, _ = run_script("import_chapter_grill.py", [
        str(vault_root), str(voyager_path)
    ])
    rc2, out2, _ = run_script("import_chapter_grill.py", [
        str(vault_root), str(voyager_path)
    ])

    assert rc1 == 0
    assert rc2 == 0
    path1 = json.loads(out1)["report_path"]
    path2 = json.loads(out2)["report_path"]
    assert path1.endswith("2026-04-10-01-计算机系统概述.md")
    assert path2.endswith("2026-04-10-01-计算机系统概述-02.md")


def test_import_chapter_grill_reads_latest_from_fixed_inbox_and_syncs_log(vault_root):
    _write_408_knowledge_map(vault_root)
    inbox = vault_root / "资料库" / "408" / "gemini_kaoda"
    older = inbox / "older.json"
    subdir = inbox / "计组"
    subdir.mkdir(parents=True, exist_ok=True)
    newer = subdir / "newer.json"
    older.write_text(json.dumps({
        "format": "gemini-voyager.chat.v1",
        "exportedAt": "2026-04-09T02:41:32.818Z",
        "count": 1,
        "title": "older",
        "items": [{"user": "结束本章，按模板总评", "assistant": _structured_assistant_text()}],
    }, ensure_ascii=False), encoding="utf-8")
    newer.write_text(json.dumps({
        "format": "gemini-voyager.chat.v1",
        "exportedAt": "2026-04-13T02:41:32.818Z",
        "count": 1,
        "title": "newer",
        "items": [{"user": "结束本章，按模板总评", "assistant": _structured_assistant_text()}],
    }, ensure_ascii=False), encoding="utf-8")

    rc, out, _ = run_script("import_chapter_grill.py", [
        str(vault_root), "latest"
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["import_source"].endswith("newer.json")
    assert "/计组/" in data["import_source"]
    log_path = vault_root / "学习日志" / "2026-04-13.md"
    assert log_path.exists()
    log_text = log_path.read_text(encoding="utf-8")
    assert "408 章节拷打：计算机组成原理 / 01 计算机系统概述" in log_text
    assert "性能指标（CPI/MIPS/主频）的推理链条还不稳" in log_text
    assert "24小时内：重讲一次 CPU 执行时间公式" in log_text
