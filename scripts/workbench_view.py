"""自包含工作台 HTML。只渲染 payload，不修改学习记录。"""
import html


def esc(value):
    return html.escape(str(value), quote=True)


def link(item, label):
    return f'<a class="button" href="{esc(item["uri"])}">{esc(label)}</a>' if item else ''


def command(value, label="复制指令", primary=False):
    return (f'<div class="command"><button type="button" class="{"primary" if primary else ""}" '
            f'data-copy="{esc(value)}">{esc(label)}</button><code>{esc(value)}</code></div>')


def muted(value):
    return f'<p class="muted">{esc(value)}</p>'


def minutes(hours):
    return f"预计 {round(hours * 60)} 分钟" if hours is not None else "用时未填写"


def render_today(data):
    plan, week, closing = data['plan'], data['week'], data['closing']
    tasks = plan['pending']
    if not plan['current']:
        main = '<article class="focus"><div class="eyebrow">从今天开始</div><h2>先安排今天的可用时间</h2>'
        main += muted('今天还没有有效计划。告诉教练可用时长，再开始第一项任务。')
        main += command('/plan_today', '复制计划指令', True) + '</article>'
    elif tasks:
        task = tasks[0]
        main = f'<article class="focus"><div class="eyebrow">先完成这一件事 · {esc(task["subject"])}</div><h2>{esc(task["title"])}</h2>'
        main += muted(minutes(task['hours']))
        main += '<details><summary>任务说明与完成标准</summary>'
        main += ''.join(f'<p>{esc(line)}</p>' for line in task['detail'])
        main += '</details><div class="actions">' + link(plan['link'], '打开计划 · 勾选完成') + '</div></article>'
        main += '<section class="next"><h3>接下来</h3>'
        for task in tasks[1:4]:
            main += f'<div class="task-row"><div><span class="subject">{esc(task["subject"])}</span> {esc(task["title"])}</div><span class="muted nowrap">{esc(minutes(task["hours"]))}</span></div>'
        if len(tasks) > 4:
            main += muted(f'还有 {len(tasks)-4} 项，打开完整计划查看。')
        main += f'<p class="muted">原计划已勾选 {plan["done"]} 项 · 剩余 {len(tasks)} 项</p></section>'
    else:
        main = '<article class="focus"><h2>今天的计划已完成</h2>' if plan['tasks'] else '<article class="focus"><h2>今日计划还没有任务</h2>'
        main += command('/progress' if plan['tasks'] else '/plan_today', '复制收尾指令' if plan['tasks'] else '复制计划指令', True) + '</article>'
    aside = '<aside><section><h3>本周主线</h3>'
    for goal in week['goals']:
        aside += f'<p><span class="subject">{esc(goal["subject"])}</span> {esc(goal["goal"])}</p>'
    if not week['goals']:
        aside += muted('本周主目标尚未记录。')
    aside += link(week['link'], '打开本周计划') if week['link'] else command('/plan_week', '复制周计划指令')
    aside += '</section><section><h3>今天的复习</h3>'
    if data['reviews']:
        first = data['reviews'][0]
        aside += f'<p>{esc(first["subject"])} · {esc(first["chapter"])}</p>'
        aside += muted('；'.join(first['reasons']))
        aside += '<button type="button" data-go="review">查看复习队列</button>'
    else:
        aside += muted('目前没有到期题。按今日计划推进即可。')
    aside += '</section><section><h3>今日收尾</h3>'
    aside += muted(f'今日新增 {closing["new_cards"]} 张错题卡 · 复习过 {closing["reviewed_cards"]} 张旧卡')
    aside += muted(f'已记录 {closing["hours"]:g} 小时' if closing['hours'] is not None else '学习时长尚未记录')
    aside += link(closing['log_link'], '打开今日日志') + command('/progress', '复制收尾指令')
    aside += '</section></aside>'
    warnings = ''.join(f'<p class="notice">{esc(warning)}</p>' for warning in data['warnings'])
    return warnings + '<div class="today-grid"><div>' + main + '</div>' + aside + '</div>'


def subject_filter(target):
    return f'<label class="filter">科目 <select data-filter="{target}"><option value="">全部科目</option>' + ''.join(f'<option>{subject}</option>' for subject in ('数学一','408','英语一','政治')) + '</select></label>'


def render_reviews(data):
    out = '<h2>复习队列</h2>' + muted('先看反复失分和当前重点，再看薄弱状态与超期。每次只取可用时间内能完成的一组。')
    out += subject_filter('review-list') + '<div id="review-list">'
    if not data['reviews']:
        out += '<div class="empty">没有到期复习。可以去知识地图挑一个待测考点。</div>'
    for index, group in enumerate(data['reviews']):
        out += f'<details class="review-group" data-subject="{esc(group["subject"])}" {"hidden" if index >= 12 else ""}><summary><span>{esc(group["subject"])} · {esc(group["chapter"])}<br><small class="muted">复习组 {index+1}</small></span><span class="badge">{group["count"]} 道</span></summary>'
        out += muted('排序依据：' + '；'.join(group['reasons']))
        for number, card in enumerate(group['cards'], start=1):
            out += f'<article class="review-card"><h3>第 {number} 题</h3>'
            out += muted(f'{card["status"]} · 最近记录 {card["last_review"]} · 到期 {card["next_review"]}')
            out += command(card['command'], '复制出题指令')
            out += '<details><summary>查看标签与原卡（可能含解题提示）</summary><p>' + esc(card['topic']) + '</p>' + link(card['link'], '在 Obsidian 打开') + '</details></article>'
        out += '</details>'
    return out + '<p class="filter-empty muted" hidden>这个科目没有到期题。</p></div><button type="button" id="more-reviews" hidden>再看 12 组</button>'


def render_knowledge(data):
    out = '<h2>掌握与证据</h2>' + muted('空白显示为待测。“会”沿用原记录，不代表已经通过无提示验收；验证日期缺失时保持未知。')
    out += subject_filter('knowledge-list') + '<div id="knowledge-list">'
    for subject in data['knowledge']:
        counts = {status: sum(c['counts'].get(status, 0) for c in subject['chapters']) for status in ('待测','不会','半会','会')}
        badges = ''.join(f'<span class="state state-{status}">{status} {count}</span>' for status,count in counts.items())
        out += f'<details class="knowledge-subject chapter" data-subject="{esc(subject["subject"])}"><summary><span>{esc(subject["subject"])}</span><span class="status-counts">{badges}</span></summary><div class="actions">{link(subject["link"], "打开知识地图")}</div>'
        if not subject['chapters']:
            out += '<p class="muted">尚无知识地图数据。</p>'
        for chapter in subject['chapters']:
            out += f'<details class="chapter"><summary><span>{esc(chapter["module"])} · {esc(chapter["name"])}</span><span class="status-counts">'
            for status in ('待测', '不会', '半会', '会'):
                if chapter['counts'].get(status):
                    out += f'<span class="state state-{status}">{status} {chapter["counts"][status]}</span>'
            out += '</span></summary>'
            for topic in chapter['topics']:
                out += f'<div class="topic"><div class="section-heading"><span>{esc(topic["name"])}</span><span class="state state-{topic["status"]}">{topic["status"]}</span></div>'
                out += '<details><summary>证据与下一步</summary>'
                for item in topic['evidence']:
                    out += f'<p>{esc(item["description"])}<span class="muted"> · 暴露于 {esc(item["date"])}</span></p>'
                    out += muted('关联卡最近记录：' + item['last_review'] if item['last_review'] else '未找到关联题卡的验证日期')
                    if item['resolved']:
                        out += muted('备注标记解决于：' + item['resolved'])
                    out += link(item['link'], '查看证据原卡')
                if topic['note']:
                    # 备注中的 HTML/Markdown 只作为文字，完整公式由 Obsidian 渲染。
                    out += f'<p class="note-text">{esc(topic["note"])}</p>'
                if not topic['evidence']:
                    out += muted('缺少可关联的测试日期与题卡；可通过小测补充证据。')
                out += command(topic['command'], '复制小测指令') + '</details></div>'
            out += '</details>'
        out += '</details>'
    return out + '</div>'


def render_progress(payload, statistics_href):
    data = payload['workbench']
    out = '<h2>本周进展与复盘</h2><h3>教材推进</h3>'
    if not data['week']['textbooks']:
        out += muted('本周尚未填写教材进度目标。')
    for row in data['week']['textbooks']:
        out += f'<div class="task-row"><span>{esc(row["name"])}</span><span>当前 {esc(row["current"])} / 目标 {esc(row["end"])}</span></div>'
        out += muted(row['note'] or ('页码目标已达到，掌握情况仍需验收。' if row['done'] else f'按剩余天数折算约 {row["today_pages"]} 页/天；不代表实际耗时。'))
    out += link(data['week']['link'], '更新教材进度')
    out += '<h3 class="spaced">最近单科成绩</h3>'
    for key, title in [('math1','数学一'),('408','408'),('english1','英语一'),('politics','政治')]:
        latest = payload['score_trends'][key]['latest']
        if latest:
            out += f'<div class="task-row"><span>{title}</span><span>{esc(latest["total_score"])} 分 · {esc(latest["exam_date"])}</span></div>'
            out += muted(latest.get('paper_label') or latest.get('paper') or '卷子未注明')
        else:
            out += f'<div class="task-row"><span>{title}</span><span class="muted">尚无整卷成绩</span></div>'
    out += muted('比较成绩前，核对卷型、首刷/复刷和限时条件。当前不自动推断这些条件。')
    out += f'<a class="button" href="{esc(statistics_href)}#score-trends">查看成绩趋势与历史统计</a>'
    out += '<div class="actions spaced">' + command('/recap week', '复制周复盘指令') + command('/score', '复制成绩记录指令') + '</div>'
    return out


CSS = r'''
:root{color-scheme:light dark;--bg:light-dark(#f4f5f7,#171b21);--paper:light-dark(#fff,#212731);--ink:light-dark(#253148,#e5ebf5);--muted:light-dark(#647086,#aab7c9);--line:light-dark(#dce2ec,#394453);--accent:light-dark(#345da5,#b1cbff);--tint:light-dark(#eef3fd,#293851)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--accent);text-decoration:none}button,a.button,select{font:inherit;color:var(--ink);background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:8px 13px;cursor:pointer}button:hover,a.button:hover{background:var(--tint)}a.button{display:inline-block}.primary{background:var(--ink);color:var(--paper);border-color:var(--ink)}.primary:hover{background:var(--accent);color:var(--paper)}.shell{max-width:1180px;margin:auto;padding:30px 28px 60px}.top{display:flex;justify-content:space-between;gap:24px;align-items:start}.brand{font-weight:600;font-size:22px;letter-spacing:-.4px}.muted,.subject{color:var(--muted)}.muted{font-size:13px}.meta{font-size:13px;color:var(--muted);margin-top:5px}.nav{display:flex;flex-wrap:wrap;gap:6px;border-bottom:1px solid var(--line);margin:23px 0 26px;padding-bottom:12px}.nav button{background:transparent;border-color:transparent}.nav button[aria-pressed=true]{background:var(--paper);border-color:var(--line);font-weight:600}h2{font-size:25px;line-height:1.4;letter-spacing:-.4px;margin:0 0 12px}h3{font-size:16px;line-height:1.5;margin:0 0 9px}p{margin:8px 0}section[hidden],[hidden]{display:none!important}.today-grid{display:grid;grid-template-columns:minmax(0,1.8fr) minmax(260px,1fr);gap:34px}.today-grid>*{min-width:0}.focus{border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:12px;background:var(--paper);padding:26px}.eyebrow{font-size:13px;color:var(--accent);margin-bottom:15px}.next{margin-top:28px}.task-row{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:14px 0;border-bottom:1px solid var(--line)}.task-row>div,.task-row>span{min-width:0;overflow-wrap:anywhere}.nowrap{white-space:nowrap}.actions{display:flex;gap:10px;align-items:start;flex-wrap:wrap;margin-top:18px}.command{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0}.command code{color:var(--muted);font:12px/1.6 ui-monospace,monospace;overflow-wrap:anywhere;max-width:100%;user-select:all}.command button{flex-shrink:0}aside{border-left:1px solid var(--line);padding-left:28px}aside section+section{border-top:1px solid var(--line);padding-top:22px;margin-top:22px}details{margin-top:12px}summary{cursor:pointer;overflow-wrap:anywhere}summary:focus-visible,button:focus-visible,a:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:4px}.notice{padding:12px 16px;border-left:3px solid var(--accent);background:var(--tint);font-size:13px;margin-bottom:18px}.filter{display:flex;align-items:center;gap:12px;margin:18px 0}.review-group,.chapter{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:12px}.review-group>summary,.chapter>summary{display:flex;justify-content:space-between;align-items:start;gap:16px;list-style:none}.review-group>summary:before,.chapter>summary:before{content:'+';color:var(--muted);flex-shrink:0}.review-group[open]>summary:before,.chapter[open]>summary:before{content:'−'}.review-group>summary>span:first-of-type,.chapter>summary>span:first-of-type{flex:1}.badge,.state{display:inline-block;background:var(--tint);color:var(--accent);border-radius:5px;padding:2px 8px;font-size:12px;white-space:nowrap}.review-card,.topic{border-top:1px solid var(--line);padding:17px 0 4px;margin-top:16px}.review-card .command{margin-bottom:0}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:14px}.knowledge-subject+.knowledge-subject{margin-top:30px}.status-counts{display:flex;gap:5px;flex-wrap:wrap}.state-待测{background:var(--bg);color:var(--muted)}.state-不会{background:light-dark(#fff0eb,#442e2a);color:light-dark(#963c23,#ffbcaa)}.state-会{background:light-dark(#eaf5ef,#253b32);color:light-dark(#286343,#a0d6b7)}.note-text{white-space:pre-line;overflow-wrap:anywhere;font-size:13px}.spaced{margin-top:28px}.empty{padding:30px 0;color:var(--muted)}footer{margin-top:40px;border-top:1px solid var(--line);padding-top:16px;font-size:12px;color:var(--muted)}#copy-status:empty{display:none}#copy-status{background:var(--tint);padding:10px 14px;border-radius:8px;margin:0 0 18px}.refresh{font-size:13px;max-width:270px}.refresh summary{color:var(--muted)}
@media(max-width:760px){.shell{padding:20px 18px 40px}.today-grid{grid-template-columns:1fr;gap:26px}aside{padding:23px 0 0;border-left:0;border-top:1px solid var(--line)}.top{flex-wrap:wrap;gap:8px}.refresh{max-width:none}.focus{padding:20px}h2{font-size:22px}.task-row{align-items:start;flex-wrap:wrap;gap:5px}.chapter>summary{flex-wrap:wrap}.status-counts{width:100%;padding-left:25px}.section-heading{flex-wrap:wrap}}@media(pointer:coarse){button,a.button,select,summary{min-height:44px}}
'''


JS = r'''
const pages=['today','review','knowledge','progress'];
function navigate(name){if(!pages.includes(name))name='today';for(const page of pages){document.getElementById('page-'+page).hidden=page!==name;document.querySelector('[data-page="'+page+'"]').setAttribute('aria-pressed',String(page===name));}history.replaceState(null,'','#'+name);window.scrollTo(0,0);}
document.querySelectorAll('[data-page],[data-go]').forEach(button=>button.addEventListener('click',()=>navigate(button.dataset.page||button.dataset.go)));
window.addEventListener('hashchange',()=>navigate(location.hash.slice(1)));
navigate(location.hash.slice(1));
document.querySelectorAll('[data-copy]').forEach(button=>button.addEventListener('click',async()=>{const status=document.getElementById('copy-status');try{await navigator.clipboard.writeText(button.dataset.copy);status.textContent='已复制，请粘贴到教练对话中执行。';}catch(error){status.textContent='浏览器未允许复制。请选中按钮旁的指令，手动复制到教练对话。';}}));
let reviewLimit=12;
function filterList(select){const list=document.getElementById(select.dataset.filter);let count=0;list.querySelectorAll('[data-subject]').forEach(item=>{const matches=!select.value||item.dataset.subject===select.value;item.hidden=!matches||(select.dataset.filter==='review-list'&&count>=reviewLimit);if(matches)count++;if(select.dataset.filter==='knowledge-list'&&select.value)item.open=matches;});const empty=list.querySelector('.filter-empty');if(empty)empty.hidden=count>0;if(select.dataset.filter==='review-list')document.getElementById('more-reviews').hidden=count<=reviewLimit;}
document.querySelectorAll('[data-filter]').forEach(select=>{select.addEventListener('change',()=>{reviewLimit=12;filterList(select);});filterList(select);});
document.getElementById('more-reviews').addEventListener('click',()=>{reviewLimit+=12;filterList(document.querySelector('[data-filter="review-list"]'));});
const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
const current=['year','month','day'].map(type=>parts.find(part=>part.type===type).value).join('-');
if(document.body.dataset.date!==current){const warning=document.getElementById('stale');warning.hidden=false;warning.textContent='这是 '+document.body.dataset.date+' 的快照。执行 /desk 重建后，再重新打开页面。';}
'''


def render_workbench(payload, statistics_href):
    data = payload['workbench']
    sections = [('today','今天',render_today(data)),('review','复习',render_reviews(data)),('knowledge','知识地图',render_knowledge(data)),('progress','进展与复盘',render_progress(payload, statistics_href))]
    nav = ''.join(f'<button type="button" data-page="{name}" aria-controls="page-{name}" aria-pressed="{str(name == "today").lower()}">{label}</button>' for name,label,_ in sections)
    panels = ''.join(f'<section id="page-{name}" aria-label="{label}" {"hidden" if name != "today" else ""}>{content}</section>' for name,label,content in sections)
    missing = '<p class="notice">还没有学习者档案。先执行 /load 建档，再安排今天。</p>' if not payload['archive']['exists'] else ''
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>考研 · 学习工作台</title><style>{CSS}</style></head>
<body data-date="{esc(payload['today'])}"><div class="shell">
<header class="top"><div><div class="brand">考研 · 学习工作台</div><div class="meta">{esc(payload['today'])} · {esc(payload['overview']['stage'] or '当前阶段未记录')}</div></div>
<details class="refresh"><summary>数据更新于 {esc(payload['generated_at'].replace('T',' '))}</summary><p>这是本地快照。学习记录更新后，由教练重新生成；浏览器刷新不会重新扫描学习库。</p>{command('/desk','复制刷新指令')}</details></header>
<nav class="nav" aria-label="工作台页面">{nav}</nav>
<div id="stale" class="notice" hidden></div><div id="copy-status" role="status" aria-live="polite"></div>{missing}<main>{panels}</main>
<footer>学习记录保存在 Obsidian。指令需粘贴到教练对话中执行；勾选任务请打开原计划。<br><a href="{esc(statistics_href)}">历史统计与成绩趋势</a> · {link(data['archive_link'],'学习者档案')}</footer>
</div><script>{JS}</script></body></html>'''
