import json, pathlib, datetime
HERE = pathlib.Path(__file__).resolve().parent
_src = HERE / "records_cov.json"
recs = json.load(open(_src if _src.exists() else HERE / "records.json"))
asof = datetime.date.today().isoformat()

CATC = {"Entertain": "#6366f1", "Micro Local": "#10b981", "คู่รัก": "#ec4899", "?": "#94a3b8"}
# engagement now = likes + comments + shares + saves
for r in recs:
    r["engagement"] = r["likes"] + r["comments"] + r["shares"] + r.get("saves", 0)
tv = sum(r["views"] for r in recs)
te = sum(r["engagement"] for r in recs)
reach = sum(r["followers"] for r in recs)
er = te / tv * 100 if tv else 0
kols = len({r["username"] for r in recs})

html = """<!DOCTYPE html>
<html lang="th"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PAO Super Perfume 2026 — Campaign Report</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#f4f6fa;--card:#fff;--line:#e5e7eb;--muted:#64748b;--text:#0f172a}
html,body{background:var(--bg);color:var(--text);font-family:'Noto Sans Thai',system-ui,sans-serif}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:0 1px 3px rgba(15,23,42,.05)}
a{color:#2563eb}.chip{padding:.15rem .6rem;border-radius:999px;font-size:.72rem;color:#fff;font-weight:600}
table th{cursor:pointer;user-select:none;white-space:nowrap}
.seg{padding:.3rem .8rem;border-radius:999px;font-size:.8rem;border:1px solid var(--line);background:#fff;cursor:pointer;transition:.15s}
.seg:hover{border-color:#94a3b8}
.nav{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;margin-bottom:1rem}
.nav-brand{font-weight:700;font-size:.95rem;margin-right:.6rem}
.navtab{padding:.4rem .9rem;border-radius:999px;font-size:.85rem;font-weight:600;color:#475569;text-decoration:none;border:1px solid var(--line);background:#fff}
.navtab:hover{background:#eef2f7}
.navtab-active{background:#0f172a;color:#fff;border-color:#0f172a}
::-webkit-scrollbar{height:8px;width:8px}::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:8px}
</style></head><body class="min-h-screen">
<div class="max-w-7xl mx-auto px-3 sm:px-5 py-5">
<nav class="nav">
<span class="nav-brand">📊 Sahagroup KOL Hub</span>
<a href="/" class="navtab">KOL Tracker</a>
<a href="/report" class="navtab navtab-active">PAO Report</a>
</nav>
<header class="mb-5">
<h1 class="text-xl sm:text-3xl font-bold">🧴 PAO Super Perfume 2026 — Campaign Report</h1>
<p class="text-sm" style="color:var(--muted)">สรุปผล KOL/Influencer TikTok · ดึง stat ล่าสุด ณ __ASOF__ · __N__ โพสต์ · ข้อมูลจริงจาก TikTok ผ่าน Apify</p>
</header>

<div id="kpis" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4"></div>

<h2 class="text-sm font-semibold mb-2" style="color:var(--muted)">รายละเอียด Engagement (like + comment + share + save)</h2>
<div id="engbreak" class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5"></div>

<section class="card p-4 mb-5">
<div class="flex flex-wrap items-center justify-between gap-3 mb-3">
<h3 class="font-semibold text-lg">🏆 Top 3 KOL</h3>
<div id="tpMetrics" class="flex flex-wrap gap-2"></div>
</div>
<div id="tpGroups" class="flex flex-wrap gap-2 mb-4"></div>
<div id="podium" class="grid grid-cols-1 sm:grid-cols-3 gap-3"></div>
</section>

<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
<div class="card p-4"><h3 class="font-semibold mb-1">Views ตามหมวด KOL</h3><div id="cDonut" style="height:300px"></div></div>
<div class="card p-4"><h3 class="font-semibold mb-1">Engagement Rate ตามหมวด</h3><div id="cER" style="height:300px"></div></div>
<div class="card p-4 lg:col-span-2"><h3 class="font-semibold mb-1">Engagement แยกชนิดตามหมวด (like / comment / share / save)</h3><div id="cStack" style="height:320px"></div></div>
<div class="card p-4 lg:col-span-2"><h3 class="font-semibold mb-1">Top 10 โพสต์ (ตาม Views)</h3><div id="cTop" style="height:380px"></div></div>
<div class="card p-4 lg:col-span-2"><h3 class="font-semibold mb-1">Followers vs Views (ประสิทธิภาพต่อฐาน follower)</h3><div id="cScatter" style="height:340px"></div></div>
</div>
<div class="card p-4">
<div class="flex items-center justify-between gap-2 mb-2"><h3 class="font-semibold">รายโพสต์ทั้งหมด (คลิกหัวคอลัมน์เพื่อจัดเรียง)</h3><button id="csv" class="seg">⬇ ดาวน์โหลด CSV</button></div>
<div class="overflow-x-auto"><table class="w-full text-sm" id="tbl"><thead><tr style="color:var(--muted)" class="text-left border-b" >
<th class="py-2 pr-3" data-k="category">หมวด</th><th class="pr-3" data-k="username">KOL</th>
<th class="pr-3 text-right" data-k="followers">Followers</th><th class="pr-3 text-right" data-k="views">Views</th>
<th class="pr-3 text-right" data-k="likes">❤️ Likes</th><th class="pr-3 text-right" data-k="comments">💬 Cmt</th>
<th class="pr-3 text-right" data-k="shares">🔁 Share</th><th class="pr-3 text-right" data-k="saves">🔖 Save</th>
<th class="pr-3 text-right" data-k="er">ER%</th>
<th class="pr-3" data-k="posted">โพสต์เมื่อ</th><th>ลิงก์</th></tr></thead><tbody id="tb"></tbody></table></div>
</div>
<footer class="text-xs mt-5" style="color:var(--muted)">สร้างโดยระบบ KOL TikTok Tracker · ตัวเลขเป็น snapshot ณ เวลาที่ดึง · ER = engagement(like+cmt+share+save)/views · Facebook 12 ลิงก์ในไฟล์ต้นฉบับใช้ actor แยก (ไม่รวมในรายงานนี้)</footer>
</div>
<script>
const DATA=__DATA__;
const CATC=__CATC__;
const fmt=n=>n>=1e6?(n/1e6).toFixed(2)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':(''+n);
// enriched: engagement = like+cmt+share+save, er per post
const E=DATA.map(r=>{const eng=r.likes+r.comments+r.shares+(r.saves||0);return {...r,engagement:eng,er:r.views?eng/r.views*100:0};});
const sum=k=>E.reduce((s,r)=>s+(r[k]||0),0);
const tv=sum('views'), te=sum('engagement');

// ---- main KPIs ----
const kpi=(l,v,s)=>`<div class="card p-3"><div class="text-xs" style="color:var(--muted)">${l}</div><div class="text-xl sm:text-2xl font-bold mt-1">${v}</div><div class="text-xs mt-1" style="color:var(--muted)">${s||''}</div></div>`;
document.getElementById('kpis').innerHTML=[
 kpi('Total Views',fmt(tv),E.length+' โพสต์'),
 kpi('Total Engagement',fmt(te),'like+cmt+share+save'),
 kpi('Avg ER',(te/tv*100).toFixed(2)+'%','engagement/views'),
 kpi('โพสต์',E.length,''),
 kpi('KOL',new Set(E.map(r=>r.username)).size,''),
 kpi('Followers รวม',fmt(sum('followers')),'reach'),
].join('');

// ---- engagement breakdown ----
const ebk=(emoji,l,k)=>{const v=sum(k);return `<div class="card p-3"><div class="text-xs" style="color:var(--muted)">${emoji} ${l}</div><div class="text-xl font-bold mt-1">${fmt(v)}</div><div class="text-xs mt-1" style="color:var(--muted)">${te?(v/te*100).toFixed(1):0}% ของ engagement</div></div>`;};
document.getElementById('engbreak').innerHTML=[ebk('❤️','Likes','likes'),ebk('💬','Comments','comments'),ebk('🔁','Shares','shares'),ebk('🔖','Saves','saves')].join('');

// ---- Top 3 KOL (group + metric filter) ----
const cats=[...new Set(E.map(r=>r.category))];
const GROUPS=['ทั้งหมด',...cats];
const METRICS=[['views','Views',fmt],['engagement','Engagement',fmt],['er','ER%',v=>v.toFixed(2)+'%'],['likes','Likes',fmt],['saves','Saves',fmt]];
let tpGroup='ทั้งหมด', tpMetric='views';
function segs(id,items,cur,cb){
 const el=document.getElementById(id);
 el.innerHTML=items.map(it=>`<button class="seg" data-v="${it.v}" style="${it.v===cur?'background:#0f172a;color:#fff;border-color:#0f172a':''}">${it.l}</button>`).join('');
 el.querySelectorAll('button').forEach(b=>b.onclick=()=>cb(b.dataset.v));
}
function podium(){
 const pool=tpGroup==='ทั้งหมด'?E:E.filter(r=>r.category===tpGroup);
 const m=METRICS.find(x=>x[0]===tpMetric);
 const top=[...pool].sort((a,b)=>b[tpMetric]-a[tpMetric]).slice(0,3);
 const medal=['🥇','🥈','🥉'];
 let cards=top.map((r,i)=>`
 <div class="card overflow-hidden" style="${i===0?'border:2px solid '+CATC[r.category]:''}">
  <a href="${r.url}" target="_blank" class="block relative group">
   ${r.thumb?`<img src="${r.thumb}" loading="lazy" style="width:100%;height:190px;object-fit:cover;display:block">`:`<div style="width:100%;height:190px;background:#e2e8f0"></div>`}
   <div class="absolute top-2 left-2 text-3xl" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,.6))">${medal[i]}</div>
   <span class="chip absolute top-3 right-2" style="background:${CATC[r.category]}">${r.category}</span>
   <div class="absolute inset-x-0 bottom-0 px-3 py-2 text-white text-sm font-semibold" style="background:linear-gradient(transparent,rgba(0,0,0,.7))">▶ ดูคลิปจริง</div>
  </a>
  <div class="p-3">
   <div class="font-bold text-lg leading-tight">@${r.username}</div>
   <div class="text-xs truncate" style="color:var(--muted)">${r.nickname||''}</div>
   <div class="mt-2 text-2xl font-extrabold" style="color:${CATC[r.category]}">${m[2](r[tpMetric])}</div>
   <div class="text-xs" style="color:var(--muted)">${m[1]}</div>
   <div class="grid grid-cols-3 gap-y-1 mt-3 text-xs" style="color:#334155">
    <div>👁 ${fmt(r.views)}</div><div>❤️ ${fmt(r.likes)}</div><div>💬 ${fmt(r.comments)}</div>
    <div>🔁 ${fmt(r.shares)}</div><div>🔖 ${fmt(r.saves||0)}</div><div>📊 ${r.er.toFixed(2)}%</div>
   </div>
  </div>
 </div>`).join('');
 if(top.length===0){cards='<div class="text-sm" style="color:var(--muted)">ไม่มีข้อมูลในกลุ่มนี้</div>';}
 else if(pool.length<3){cards+=`<div class="card p-4 flex flex-col items-center justify-center text-center" style="color:var(--muted);border-style:dashed">
   <div class="text-2xl mb-1">ℹ️</div><div class="text-sm">กลุ่ม "<b>${tpGroup}</b>" มี KOL แค่ <b>${pool.length}</b> ราย<br>จึงแสดงได้ ${pool.length} อันดับ</div></div>`;}
 document.getElementById('podium').innerHTML=cards;
}
function drawTP(){
 segs('tpGroups',GROUPS.map(g=>({v:g,l:g})),tpGroup,v=>{tpGroup=v;drawTP();});
 segs('tpMetrics',METRICS.map(m=>({v:m[0],l:m[1]})),tpMetric,v=>{tpMetric=v;drawTP();});
 podium();
}
drawTP();

// ---- charts ----
const AX={axisLine:{lineStyle:{color:'#cbd5e1'}},axisLabel:{color:'#64748b'},splitLine:{lineStyle:{color:'#eef2f7'}}};
const byCat={};E.forEach(r=>{byCat[r.category]=byCat[r.category]||{v:0,e:0,n:0};byCat[r.category].v+=r.views;byCat[r.category].e+=r.engagement;byCat[r.category].n++;});
echarts.init(document.getElementById('cDonut')).setOption({tooltip:{trigger:'item',valueFormatter:fmt},
 series:[{type:'pie',radius:['45%','72%'],label:{color:'#334155'},data:cats.map(c=>({name:c,value:byCat[c].v,itemStyle:{color:CATC[c]}}))}]});
echarts.init(document.getElementById('cER')).setOption({tooltip:{trigger:'axis',valueFormatter:v=>v.toFixed(2)+'%'},grid:{left:50,right:20,top:20,bottom:25},
 xAxis:{type:'category',data:cats,...AX},yAxis:{type:'value',...AX,axisLabel:{color:'#64748b',formatter:'{value}%'}},
 series:[{type:'bar',data:cats.map(c=>({value:+(byCat[c].e/byCat[c].v*100).toFixed(2),itemStyle:{color:CATC[c]}})),barWidth:'45%'}]});
// stacked engagement by category
const EK=[['likes','Likes','#ef4444'],['comments','Comments','#f59e0b'],['shares','Shares','#3b82f6'],['saves','Saves','#8b5cf6']];
echarts.init(document.getElementById('cStack')).setOption({tooltip:{trigger:'axis',valueFormatter:fmt},legend:{bottom:0,textStyle:{color:'#475569'}},grid:{left:55,right:20,top:15,bottom:45},
 xAxis:{type:'category',data:cats,...AX},yAxis:{type:'value',...AX,axisLabel:{...AX.axisLabel,formatter:fmt}},
 series:EK.map(([k,name,col])=>({name,type:'bar',stack:'eng',barWidth:'45%',data:cats.map(c=>E.filter(r=>r.category===c).reduce((s,r)=>s+(r[k]||0),0)),itemStyle:{color:col}}))});
const top=[...E].sort((a,b)=>a.views-b.views).slice(-10);
echarts.init(document.getElementById('cTop')).setOption({tooltip:{trigger:'axis',valueFormatter:fmt},grid:{left:110,right:30,top:10,bottom:25},
 xAxis:{type:'value',...AX,axisLabel:{...AX.axisLabel,formatter:fmt}},yAxis:{type:'category',data:top.map(r=>r.username),...AX},
 series:[{type:'bar',data:top.map(r=>({value:r.views,itemStyle:{color:CATC[r.category]}}))}]});
echarts.init(document.getElementById('cScatter')).setOption({tooltip:{trigger:'item',formatter:p=>`${p.data[2]}<br>Followers: ${fmt(p.data[0])}<br>Views: ${fmt(p.data[1])}`},
 grid:{left:60,right:30,top:20,bottom:35},xAxis:{type:'log',name:'Followers',...AX,axisLabel:{...AX.axisLabel,formatter:fmt}},
 yAxis:{type:'log',name:'Views',...AX,axisLabel:{...AX.axisLabel,formatter:fmt}},
 series:[{type:'scatter',symbolSize:12,data:E.map(r=>[Math.max(r.followers,1),Math.max(r.views,1),r.username,r.category]),itemStyle:{color:p=>CATC[p.data[3]]}}]});

// ---- table ----
let sortK='views',asc=false;
function render(){const d=[...E];
 d.sort((a,b)=>{let x=a[sortK],y=b[sortK];if(typeof x==='string'){return asc?(''+x).localeCompare(y):(''+y).localeCompare(x)}return asc?x-y:y-x});
 document.getElementById('tb').innerHTML=d.map(r=>`<tr class="border-b hover:bg-black/5" style="border-color:var(--line)">
 <td class="py-2 pr-3"><span class="chip" style="background:${CATC[r.category]}">${r.category}</span></td>
 <td class="pr-3 font-medium">@${r.username||''}</td><td class="pr-3 text-right">${fmt(r.followers)}</td>
 <td class="pr-3 text-right font-semibold">${r.views.toLocaleString()}</td><td class="pr-3 text-right">${r.likes.toLocaleString()}</td>
 <td class="pr-3 text-right">${r.comments.toLocaleString()}</td><td class="pr-3 text-right">${r.shares.toLocaleString()}</td>
 <td class="pr-3 text-right">${(r.saves||0).toLocaleString()}</td>
 <td class="pr-3 text-right">${r.er.toFixed(2)}%</td><td class="pr-3" style="color:var(--muted)">${r.posted||''}</td>
 <td><a href="${r.url}" target="_blank">เปิด ↗</a></td></tr>`).join('');}
document.querySelectorAll('#tbl th').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(k){asc=sortK===k?!asc:false;sortK=k;render();}});
render();
// CSV export
document.getElementById('csv').onclick=()=>{
 const cols=['category','username','nickname','followers','views','likes','comments','shares','saves','engagement','er','posted','url'];
 const esc=v=>{v=(''+(v==null?'':v)).replace(/"/g,'""');return /[",\\n]/.test(v)?'"'+v+'"':v;};
 const lines=[cols.join(',')].concat(E.map(r=>cols.map(c=>c==='er'?r.er.toFixed(2):esc(r[c])).join(',')));
 const blob=new Blob(['﻿'+lines.join('\\n')],{type:'text/csv;charset=utf-8'});
 const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='PAO_Super_Perfume_2026.csv';a.click();
};
</script></body></html>"""

html = (html.replace("__DATA__", json.dumps(recs, ensure_ascii=False))
            .replace("__CATC__", json.dumps(CATC, ensure_ascii=False))
            .replace("__ASOF__", asof).replace("__N__", str(len(recs))))
out = HERE / "PAO_Super_Perfume_2026_Report.html"
out.write_text(html, encoding="utf-8")
print("สร้างรายงาน:", out)
print(f"KPI: Views {tv:,} | Eng {te:,} | ER {er:.2f}% | {len(recs)} โพสต์ | {kols} KOL | reach {reach:,}")
