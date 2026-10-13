"""元技能目录的 HTML 组件；所有文字经转义，浏览操作不写学习记录。"""
import html
import json


def render_metaskills(data):
    data = data or {"clusters": [], "warnings": [], "unclustered": [], "total_cards": 0, "families": 0, "singleton_count": 0}
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    md_link = data.get("markdown_uri")
    md = f'<a class="button" href="{html.escape(md_link["uri"], quote=True)}">在 Obsidian 看目录</a>' if md_link else ''
    warnings = ''.join(f'<p class="notice">{html.escape(w)}</p>' for w in data.get("warnings", []))
    return f'''<div class="ms-heading"><div><div class="eyebrow">从一道题，找到一个可迁移的动作</div><h2>元技能目录</h2>
<p class="muted">按章节找到位置，按方法串起联系。点开一个簇，查看完整决策和题目。</p></div>{md}</div>
<div class="ms-overview"><span><strong>{len(data['clusters'])}</strong> 个簇</span><span><strong>{data['total_cards']}</strong> 张题卡</span><span><strong>{data['families']}</strong> 个方法族</span><span>{data['singleton_count']} 个单题簇</span></div>
{warnings}<div class="ms-toolbar">
<label class="ms-search"><span>搜索</span><input id="ms-search" type="search" placeholder="技能、口诀、题目或簇 ID" autocomplete="off"></label>
<label><span>科目</span><select id="ms-subject"><option value="">全部科目</option></select></label>
<label><span>题数</span><select id="ms-size"><option value="">全部簇</option><option value="single">单题簇</option><option value="multi">多题簇</option></select></label>
<label><span>复习记录</span><select id="ms-record"><option value="">全部记录</option><option value="due">有到期题</option><option value="weak">有不会的题</option><option value="unknown">有未标注记录</option></select></label>
</div>
<div class="ms-layout"><div class="ms-directory"><div class="ms-modes" role="group" aria-label="目录分组方式"><button id="ms-by-chapter" type="button" aria-pressed="true">按章节</button><button id="ms-by-family" type="button" aria-pressed="false">按方法</button></div><div id="ms-groups" aria-label="目录分组"></div></div>
<div class="ms-results"><div class="ms-list-head"><strong id="ms-result-count" role="status" aria-live="polite"></strong><button id="ms-reset" type="button">重置</button></div><div id="ms-list" aria-label="元技能簇列表"></div><button id="ms-more" type="button" hidden>再看 30 个簇</button></div>
<article id="ms-detail" class="ms-detail" aria-label="选中簇的详情"></article></div>
<p class="muted ms-footnote">颜色汇总主归属卡的现有记录；次归属另列，不重复计入。单题簇尚不能证明跨题迁移。</p>
<div id="ms-unclustered"></div><script id="ms-data" type="application/json">{payload}</script>'''


CSS = r'''
.ms-heading{display:flex;justify-content:space-between;align-items:center;gap:20px}.ms-heading .eyebrow{margin-bottom:6px}.ms-heading h2{margin-bottom:4px}.ms-heading .button{flex-shrink:0}.ms-overview{display:flex;gap:22px;flex-wrap:wrap;padding:15px 0 18px;border-bottom:1px solid var(--line);font-size:13px;color:var(--muted)}.ms-overview strong{font-size:20px;color:var(--ink);margin-right:3px;font-weight:600;font-variant-numeric:tabular-nums}.ms-toolbar{display:grid;grid-template-columns:minmax(200px,1fr) 130px 120px 150px;gap:12px;margin:22px 0}.ms-toolbar label{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--muted)}.ms-toolbar input,.ms-toolbar select{width:100%;min-width:0;background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:9px 11px;color:var(--ink);font:14px/1.5 inherit}.ms-toolbar input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.ms-layout{display:grid;grid-template-columns:185px minmax(240px,.85fr) minmax(0,1.15fr);gap:20px;align-items:start}.ms-layout>*{min-width:0}.ms-directory{position:sticky;top:18px}.ms-modes{display:flex;gap:4px;padding:4px;background:var(--tint);border-radius:9px;margin-bottom:12px}.ms-modes button{flex:1;border:0;background:transparent;padding:7px 4px;font-size:13px}.ms-modes button[aria-pressed=true]{background:var(--paper);box-shadow:0 1px 3px #0001;font-weight:600}#ms-groups{max-height:65vh;overflow-y:auto;padding-right:4px}.ms-group{display:flex;justify-content:space-between;gap:6px;width:100%;text-align:left;border:0;border-radius:6px;background:transparent;padding:8px;font-size:12px;line-height:1.5;margin:3px 0}.ms-group span:first-child{min-width:0;overflow-wrap:anywhere}.ms-group span:last-child{font-variant-numeric:tabular-nums;color:var(--muted)}.ms-group[aria-pressed=true]{background:var(--tint);color:var(--accent);font-weight:600}.ms-group-label{margin:12px 8px 5px;color:var(--muted);font-size:11px;font-weight:600}.ms-list-head{display:flex;justify-content:space-between;align-items:center;font-size:13px;margin-bottom:12px}.ms-list-head button{font-size:12px;padding:4px 8px}.ms-row{display:block;width:100%;text-align:left;border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:9px;background:var(--paper)}.ms-row[aria-pressed=true]{border-color:var(--accent);box-shadow:inset 3px 0 0 var(--accent);background:var(--tint)}.ms-row-title{display:block;font-size:14px;font-weight:600;line-height:1.5;overflow-wrap:anywhere}.ms-row-meta{display:block;font-size:11px;color:var(--muted);margin-top:6px}.ms-bar{display:flex;height:5px;border-radius:3px;overflow:hidden;background:var(--line);margin-top:10px}.ms-bar>*{height:100%}.ms-segment-不会{background:light-dark(#c27b69,#d79883)}.ms-segment-半会{background:light-dark(#c8a34e,#dfbd6a)}.ms-segment-会{background:light-dark(#6e9981,#8bbda3)}.ms-segment-未标注{background:var(--muted)}.ms-row-counts{font-size:11px;color:var(--muted);margin-top:5px;display:block}#ms-more{width:100%;font-size:13px}.ms-detail{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:22px;position:sticky;top:18px;max-height:78vh;overflow-y:auto;scroll-margin-top:15px}.ms-detail h3{font-size:22px;line-height:1.4;margin:4px 0 12px}.ms-detail h4{font-size:13px;margin:22px 0 8px;color:var(--muted);font-weight:600}.ms-id{font:11px/1.5 ui-monospace,monospace;color:var(--muted);letter-spacing:.04em}.ms-decision{font-size:14px;line-height:1.9;overflow-wrap:anywhere;white-space:pre-line}.ms-card{border-top:1px solid var(--line);padding:13px 0;overflow-wrap:anywhere}.ms-card a{display:block;font-size:14px;line-height:1.5;margin-top:6px}.ms-card .command{margin-bottom:0}.ms-card button{font-size:12px;padding:5px 8px}.ms-tags{display:flex;flex-wrap:wrap;gap:5px;align-items:center}.state-半会{background:light-dark(#fff6de,#423a26);color:light-dark(#85631f,#e3c777)}.ms-peer{font-size:12px;margin:4px 5px 4px 0;padding:6px 9px;max-width:100%;white-space:normal;text-align:left}.ms-footnote{margin-top:18px}.ms-detail .katex{font-size:1em}.ms-detail .katex-display{overflow-x:auto;overflow-y:hidden}.ms-secondary-info{font-size:11px;color:var(--muted);margin-top:7px}.ms-empty{padding:22px 8px;font-size:14px;color:var(--muted)}
@media(min-width:1280px){body:has(#page-metaskills:not([hidden])) .shell{max-width:1360px}.ms-layout{grid-template-columns:210px minmax(280px,.85fr) minmax(0,1.15fr)}}
@media(max-width:980px){.ms-layout{grid-template-columns:160px minmax(0,1fr)}.ms-detail{grid-column:1/-1;position:static;max-height:none}.ms-directory{position:static}#ms-groups{max-height:430px}}
@media(max-width:600px){.ms-heading{align-items:start;flex-direction:column;gap:8px}.ms-overview{gap:12px}.ms-toolbar{grid-template-columns:1fr 1fr;gap:10px}.ms-search{grid-column:1/-1}.ms-layout{display:block}.ms-directory{margin-bottom:16px}#ms-groups{max-height:180px;border-bottom:1px solid var(--line);padding-bottom:8px}.ms-group{padding:8px 10px}.ms-group-label{margin-top:8px}.ms-detail{padding:18px;margin-top:20px}.ms-results{min-width:0}.ms-row{padding:12px}.ms-detail h3{font-size:20px}}
'''


JS = r'''
(()=>{
const source=document.getElementById('ms-data');if(!source)return;
const data=JSON.parse(source.textContent),rows=data.clusters;
const $=id=>document.getElementById(id),h=x=>String(x??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const state={mode:'chapter_group',group:'',selected:null,limit:30};
const statuses=['不会','半会','会','未标注'];
const badges=c=>statuses.filter(s=>c.counts[s]).map(s=>`<span class="state state-${s}">${s} ${c.counts[s]}</span>`).join('');
const cardLink=m=>m.link?`<a href="${h(m.link.uri)}">${h(m.topic)} ↗</a>`:`<p>${h(m.topic)}</p>`;
const terms=c=>[c.name,c.skill,c.id,c.family,c.chapter_group,...c.members.map(m=>m.topic+' '+m.qid)].join(' ').toLowerCase();
const searches=new Map(rows.map(c=>[c.id,terms(c)]));
for(const subject of [...new Set(rows.map(c=>c.subject))]){$('ms-subject').insertAdjacentHTML('beforeend',`<option value="${h(subject)}">${h(subject)}</option>`);}
function baseMatches(c){
const query=$('ms-search').value.trim().toLowerCase().split(/\s+/).filter(Boolean),subject=$('ms-subject').value,size=$('ms-size').value,record=$('ms-record').value;
return query.every(q=>searches.get(c.id).includes(q))&&(!subject||subject===c.subject)&&(!size||(size==='single'?c.primary_count===1:c.primary_count>1))&&(!record||(record==='due'?c.due_count>0:record==='weak'?c.counts['不会']>0:c.counts['未标注']>0));
}
function renderGroups(base){
const groups=new Map();for(const c of base)groups.set(c[state.mode],(groups.get(c[state.mode])||0)+1);
const top=`<button class="ms-group" type="button" data-ms-group="" aria-pressed="${!state.group}"><span>全部${state.mode==='family'?'方法':'章节'}</span><span>${base.length}</span></button>`;
let previous='',body='';
const groupRank=g=>state.mode==='family'?0:g.startsWith('数学一 · 高数')?0:g.startsWith('数学一 · 线代')?1:g.startsWith('数学一 · 概率统计')?2:g.startsWith('408')?3:4;
const entries=[...groups].sort((a,b)=>groupRank(a[0])-groupRank(b[0])||a[0].localeCompare(b[0],'zh-CN',{numeric:true}));
for(const [group,n]of entries){let label=group;
if(state.mode==='chapter_group'){const parts=group.split(' · '),category=parts.slice(0,2).join(' · ');if(category!==previous){body+=`<div class="ms-group-label">${h(category)}</div>`;previous=category;}label=parts.slice(2).join(' · ');}
body+=`<button class="ms-group" type="button" data-ms-group="${h(group)}" aria-pressed="${state.group===group}"><span>${h(label)}</span><span>${n}</span></button>`;
}
$('ms-groups').innerHTML=top+body;
}
function draw(){
const base=rows.filter(baseMatches);renderGroups(base);const visible=base.filter(c=>!state.group||c[state.mode]===state.group);
$('ms-result-count').textContent=`找到 ${visible.length} 个簇`;
if(!visible.some(c=>c.id===state.selected))state.selected=visible[0]?.id||null;
$('ms-list').innerHTML=visible.slice(0,state.limit).map(c=>{
const total=Object.values(c.counts).reduce((a,b)=>a+b,0),bar=statuses.filter(s=>c.counts[s]).map(s=>`<span class="ms-segment-${s}" style="width:${100*c.counts[s]/(total||1)}%"></span>`).join('');
return `<button class="ms-row" type="button" data-ms-select="${h(c.id)}" aria-pressed="${c.id===state.selected}" aria-controls="ms-detail"><span class="ms-row-title">${h(c.name)}</span><span class="ms-row-meta">${h(c.id)} · 主归属 ${c.primary_count} 题${c.secondary_count?` · 次归属 ${c.secondary_count} 题`:''} · 到期 ${c.due_count}</span><span class="ms-bar" aria-hidden="true">${bar}</span><span class="ms-row-counts">${h(statuses.filter(s=>c.counts[s]).map(s=>s+' '+c.counts[s]).join(' · ')||'暂无可读记录')}</span></button>`;
}).join('')||'<p class="ms-empty">没有匹配的簇。试试其他关键词，或重置筛选。</p>';
$('ms-more').hidden=visible.length<=state.limit;renderDetail();
}
function renderDetail(){
const c=rows.find(c=>c.id===state.selected),panel=$('ms-detail');
if(!c){panel.innerHTML='<p class="ms-empty">选中一个簇后，在这里查看解题决策和成员题目。</p>';return;}
const arrow=c.skill.indexOf('→'),decision=arrow<0?`<p class="ms-decision">${h(c.skill)}</p>`:`<h4>看到什么</h4><p class="ms-decision">${h(c.skill.slice(0,arrow).trim())}</p><h4>做什么 · 适用边界</h4><p class="ms-decision">${h(c.skill.slice(arrow+1).trim())}</p>`;
const main=c.members.filter(m=>m.role==='主归属'),secondary=c.members.filter(m=>m.role==='次归属');
function members(items){return items.map(m=>`<div class="ms-card"><div class="ms-tags"><span class="state state-${h(m.status)}">${h(m.status)}</span>${m.due?'<span class="badge">到期</span>':''}${m.missing?'<span class="badge">未读到</span>':''}</div>${cardLink(m)}<div class="muted">最近记录 ${h(m.last_review)} · 复习日期 ${h(m.next_review)}</div>${m.role==='次归属'?`<div class="ms-secondary-info">主归属：${m.primary_clusters.map(cid=>`<button class="ms-peer" type="button" data-ms-jump="${h(cid)}">${h(rows.find(x=>x.id===cid)?.name||cid)}</button>`).join('')}</div>`:''}<div class="command"><button type="button" data-ms-copy="${h(m.command)}">复制单题复习指令</button><code>${h(m.command)}</code></div></div>`).join('');}
const peers=rows.filter(s=>s.family===c.family&&s.id!==c.id);
panel.innerHTML=`<div class="ms-id">${h(c.id)}</div><h3>${h(c.name)}</h3><p class="muted">${h(c.chapter_group)}</p><div class="ms-tags">${badges(c)}<span class="badge">到期 ${c.due_count}</span></div>${decision}${c.note?`<p class="notice">${h(c.note)}</p>`:''}<h4>主归属题目 · ${main.length}</h4>${members(main)}${secondary.length?`<h4>次归属题目 · ${secondary.length}</h4><p class="muted">也使用这个动作；状态不重复计入本簇。</p>${members(secondary)}`:''}<h4>同方法族 · ${h(c.family)}</h4><p class="muted">方法相关，具体触发条件不同。</p>${peers.map(s=>`<button class="ms-peer" type="button" data-ms-jump="${h(s.id)}">${h(s.name)} · ${h(s.id)}</button>`).join('')||'<p class="muted">目前没有其他同方法族簇。</p>'}`;
panel.scrollTop=0;
if(window.renderMathInElement)window.renderMathInElement(panel,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],throwOnError:false,trust:false,strict:'ignore'});
}
$('ms-search').addEventListener('input',()=>{state.group='';state.limit=30;draw();});
for(const id of ['ms-subject','ms-size','ms-record'])$(id).addEventListener('change',()=>{state.group='';state.limit=30;draw();});
for(const [id,mode]of [['ms-by-chapter','chapter_group'],['ms-by-family','family']])$(id).addEventListener('click',()=>{state.mode=mode;state.group='';state.limit=30;$('ms-by-chapter').setAttribute('aria-pressed',String(mode==='chapter_group'));$('ms-by-family').setAttribute('aria-pressed',String(mode==='family'));draw();});
$('ms-reset').addEventListener('click',()=>{for(const id of ['ms-search','ms-subject','ms-size','ms-record'])$(id).value='';state.group='';state.limit=30;draw();});
$('ms-more').addEventListener('click',()=>{state.limit+=30;draw();});
document.getElementById('page-metaskills').addEventListener('click',async event=>{
const group=event.target.closest('[data-ms-group]'),select=event.target.closest('[data-ms-select]'),jump=event.target.closest('[data-ms-jump]'),copy=event.target.closest('[data-ms-copy]');
if(group){state.group=group.dataset.msGroup;state.limit=30;draw();}
if(select){state.selected=select.dataset.msSelect;draw();if(innerWidth<=980)$('ms-detail').scrollIntoView({behavior:'smooth',block:'start'});}
if(jump){for(const id of ['ms-search','ms-subject','ms-size','ms-record'])$(id).value='';state.group='';state.selected=jump.dataset.msJump;state.limit=Math.max(30,rows.findIndex(c=>c.id===state.selected)+1);draw();if(innerWidth<=980)$('ms-detail').scrollIntoView({behavior:'smooth',block:'start'});}
if(copy){const status=$('copy-status');try{await navigator.clipboard.writeText(copy.dataset.msCopy);status.textContent='已复制单题指令，请粘贴到教练对话中开始。';copy.textContent='已复制';}catch(error){copy.textContent='请选中旁边的指令复制';}}
});
if(data.unclustered.length)$('ms-unclustered').innerHTML=`<details><summary>未归类题目 · ${data.unclustered.length}</summary>${data.unclustered.map(c=>c.link?`<p><a href="${h(c.link.uri)}">${h(c.topic)}</a></p>`:`<p>${h(c.topic)}</p>`).join('')}</details>`;
draw();
})();
'''
