#!/usr/bin/env python3
"""Build a self-contained mock-draft page that needs no install and no network.

    python mock_page.py        # -> out/mock-draft.html

Everything a mock draft needs is historical: the player board and each
manager's drafting tendencies. Both are baked into the page at build time, so
the simulation runs entirely in the browser. That is what makes this shareable
as a link, where the live draft advisor cannot be -- following a real draft
means polling Sleeper, and a hosted page is not allowed to.

Whoever opens it picks which manager they are and drafts from that seat against
models of the other eleven.
"""

import json
import sys
from pathlib import Path

from draft import DRAFT_REPLACEMENT, build_board, opponent_tendencies, setup
from model import Players, _load

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out" / "mock-draft.html"

# Deep enough to draft 15 rounds and still show a real waiver-tier board
# underneath, without bloating the page.
BOARD_DEPTH = 420

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def collect():
    import types
    args = types.SimpleNamespace(slot=None, season=None, mock=True)
    state = setup(args)

    board = [{"i": p["player_id"], "n": p["name"], "p": p["pos"],
              "j": round(p["proj"], 1), "v": round(p["vor"], 1), "r": p["rank"]}
             for p in state.board[:BOARD_DEPTH]]

    tend, league = opponent_tendencies()
    rounds = state.rounds

    index = _load("index.json")
    league_id = next(s["league_id"] for s in index["seasons"]
                     if s["season"] == state.season)
    from model import Season, SLOT_ELIGIBILITY
    slots = Season(state.season, league_id).starting_slots

    def trim(d):
        return {str(r): {k: round(v, 3) for k, v in (d.get(r) or {}).items() if v > 0}
                for r in range(1, rounds + 1)}

    return {
        "season": state.season,
        "teams": state.teams,
        "rounds": rounds,
        "managers": list(state.order),
        "board": board,
        "tendencies": {m: trim(t) for m, t in tend.items()},
        "league": trim(league),
        "replacement": DRAFT_REPLACEMENT,
        "slots": slots,
        "eligible": {s: sorted(SLOT_ELIGIBILITY.get(s, [])) for s in set(slots)},
    }


PAGE = r"""<title>Mock draft room</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;
 --ink-2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
 --hairline:rgba(11,11,11,0.10);--accent:#2a78d6;--neg:#e34948;--good:#006300;
 --cQB:#2a78d6;--cRB:#eb6834;--cWR:#1baf7a;--cTE:#eda100;--cK:#e87ba4;--cDEF:#008300}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
 --page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--axis:#383835;--hairline:rgba(255,255,255,0.10);
 --accent:#3987e5;--neg:#e66767;--good:#0ca30c;
 --cQB:#3987e5;--cRB:#d95926;--cWR:#199e70;--cTE:#c98500;--cK:#d55181;--cDEF:#008300}}
:root[data-theme="dark"]{color-scheme:dark;
 --page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--axis:#383835;--hairline:rgba(255,255,255,0.10);
 --accent:#3987e5;--neg:#e66767;--good:#0ca30c;
 --cQB:#3987e5;--cRB:#d95926;--cWR:#199e70;--cTE:#c98500;--cK:#d55181;--cDEF:#008300}
*{box-sizing:border-box}
body{margin:0;padding:28px 18px 70px;background:var(--page);color:var(--ink);
 font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1380px;margin:0 auto}
h1{font-size:28px;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:19px;margin:30px 0 8px;letter-spacing:-.01em}
h3{margin:0 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-2)}
.sub{color:var(--ink-2);margin:0 0 4px}
.note{color:var(--muted);font-size:13px}
button{font:inherit;cursor:pointer;border-radius:8px;border:1px solid var(--hairline);
 background:var(--surface);color:var(--ink);padding:9px 14px}
button:hover{border-color:var(--accent)}
button.sel{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent);
 font-weight:600;padding:11px 22px;font-size:16px}
button:disabled{opacity:.45;cursor:not-allowed}
.row{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 4px}
.card{background:var(--surface);border:1px solid var(--hairline);border-radius:10px;
 padding:18px;margin-top:12px}
.turn{background:var(--accent);color:#fff;padding:13px 16px;border-radius:10px;
 font-size:17px;font-weight:600;margin-bottom:10px}
.wait{background:var(--surface);border:1px solid var(--hairline);padding:13px 16px;
 border-radius:10px;margin-bottom:10px;color:var(--ink-2)}
.warn{background:var(--neg);color:#fff;padding:10px 14px;border-radius:8px;
 font-weight:600;margin-bottom:10px}
.grid2{display:grid;grid-template-columns:1fr 300px;gap:16px;align-items:start}
@media(max-width:860px){.grid2{grid-template-columns:1fr}}
.rec{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:8px;
 border:1px solid var(--hairline);margin-bottom:6px;background:var(--surface)}
.rec.top{border-color:var(--accent);border-width:2px}
.live .rec{cursor:pointer}
.live .rec:hover{background:var(--page);border-color:var(--accent)}
.rec .nm{font-weight:600;flex:1}
.rec .ps{font-size:12px;color:var(--muted);width:32px}
.rec .num{font-size:13px;color:var(--ink-2);font-variant-numeric:tabular-nums}
.blocked{opacity:.55;font-size:13px;padding:3px 12px}
.chip{display:inline-block;background:var(--surface);border:1px solid var(--hairline);
 border-radius:999px;padding:2px 10px;margin:2px 4px 2px 0;font-size:13px}
.pool{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:10px}
.av{padding:3px 8px;border-radius:5px;font-size:13px;display:flex;gap:8px;
 border-left:3px solid var(--muted)}
.live .av{cursor:pointer}
.live .av:hover{background:var(--surface)}
.av .v{margin-left:auto;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.board{overflow-x:auto;padding-bottom:6px}
.board table{border-collapse:separate;border-spacing:3px;font-size:11px}
.board th{font-size:10px;font-weight:600;padding:1px 4px;color:var(--muted);white-space:nowrap}
.board th.me{color:var(--accent)}
.rd{color:var(--muted);font-variant-numeric:tabular-nums;padding-right:4px;font-size:11px}
.cell{width:104px;height:32px;border-radius:5px;background:var(--surface);
 border:1px solid var(--hairline);border-left:3px solid var(--muted);padding:3px 6px;
 overflow:hidden;line-height:1.2}
.cell.empty{background:transparent;border-style:dashed;border-left-color:var(--hairline)}
.cell.mine{box-shadow:inset 0 0 0 1px var(--accent)}
.cell .n{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.cell .p{color:var(--muted);font-size:10px}
.cQB{border-left-color:var(--cQB)}.cRB{border-left-color:var(--cRB)}
.cWR{border-left-color:var(--cWR)}.cTE{border-left-color:var(--cTE)}
.cK{border-left-color:var(--cK)}.cDEF{border-left-color:var(--cDEF)}
table.sum{border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}
table.sum td{padding:5px 14px 5px 0;border-bottom:1px solid var(--grid);
 vertical-align:top;max-width:640px}
table.ros{border-collapse:collapse;width:100%;font-size:13px}
table.ros td{padding:4px 6px 4px 0;border-bottom:1px solid var(--grid)}
table.ros tr.hole td{opacity:.6}
table.ros .sl{color:var(--muted);font-size:11px;width:42px;font-weight:600}
table.ros .num{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums}
.pill{display:inline-block;font-size:10px;font-weight:600;padding:1px 5px;border-radius:4px;
 border:1px solid var(--hairline);border-left-width:3px;color:var(--ink-2)}
.dens{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
.dens .d{font-size:12px;padding:2px 8px;border-radius:999px;background:var(--surface);
 border:1px solid var(--hairline);border-left-width:3px;color:var(--ink-2)}
.dens .d b{color:var(--ink);font-variant-numeric:tabular-nums}
details.key{margin:20px 0 0;background:var(--surface);border:1px solid var(--hairline);
 border-radius:10px;padding:12px 16px}
details.key summary{cursor:pointer;font-weight:600;color:var(--ink-2)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
<div class="wrap" id="app">Loading&hellip;</div>
<script>
(function(){
"use strict";
// Everything is wrapped and wired with addEventListener rather than inline
// onclick attributes: a host page may serve a Content-Security-Policy that
// permits a <script> block but still blocks inline handlers, which would leave
// every button dead with no visible reason.
function fail(e){
  try{
    var a=document.getElementById("app");
    if(a) a.innerHTML='<h1>Something went wrong</h1><p class="sub">'+
      String((e&&e.message)||e)+'</p><pre class="note" style="white-space:pre-wrap">'+
      String((e&&e.stack)||"")+'</pre>';
  }catch(_){}
}
window.addEventListener("error",function(ev){ fail(ev.error||ev.message); });
try{
const DATA = __DATA__;

const PRESETS = {
  value:{label:"Best available",note:"No rules. Always takes the most valuable player left.",
         earliest:{K:13,DEF:13},caps:{QB:2,TE:2,K:1,DEF:1,RB:6,WR:7},max:{}},
  hero:{label:"Hero RB, late QB",note:"One anchor back early, then let running back go. No quarterback before round 8.",
        earliest:{QB:8,TE:5,K:14,DEF:14},caps:{QB:2,TE:2,K:1,DEF:1,RB:6,WR:7},max:{RB:[5,2]}},
  robust:{label:"Robust RB",note:"Load up on running backs early and take receivers later.",
          earliest:{QB:7,TE:6,K:14,DEF:14},caps:{QB:2,TE:2,K:1,DEF:1,RB:7,WR:6},max:{WR:[3,1]}},
  zero:{label:"Zero RB",note:"No running back until round 5. Receivers and a tight end first.",
        earliest:{RB:5,QB:8,K:14,DEF:14},caps:{QB:2,TE:3,K:1,DEF:1,RB:7,WR:7},max:{}}
};
const POS = ["QB","RB","WR","TE","K","DEF"];
const BOT_CAPS = {QB:2,TE:2,RB:6,WR:6,K:1,DEF:1};

let S = null;
const esc = t => String(t).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

function slotOnClock(pk){
  const r = Math.floor((pk-1)/DATA.teams)+1, i=(pk-1)%DATA.teams;
  return [r%2===1 ? i+1 : DATA.teams-i, r];
}
function nextOwn(after){
  for(let pk=after; pk<=DATA.teams*DATA.rounds; pk++)
    if(slotOnClock(pk)[0]===S.slot) return pk;
  return null;
}
function poissonBelow(k,lam){
  if(lam<=0) return 1;
  let term=Math.exp(-lam), tot=0;
  for(let i=0;i<k;i++){ if(i) term*=lam/i; tot+=term; }
  return Math.min(1,tot);
}
function counts(roster){
  const c={}; roster.forEach(p=>{c[p.p]=(c[p.p]||0)+1;}); return c;
}
function allowed(pos,rnd,c){
  const d=PRESETS[S.preset];
  if(d.earliest[pos] && rnd<d.earliest[pos])
    return [false,"not before round "+d.earliest[pos],"timing"];
  if(d.caps[pos]!=null && (c[pos]||0)>=d.caps[pos])
    return [false,"already have "+c[pos]+" "+pos,"cap"];
  const m=d.max[pos];
  if(m && rnd<=m[0] && (c[pos]||0)>=m[1])
    return [false,"max "+m[1]+" "+pos+" through round "+m[0],"timing"];
  return [true,"",""];
}
function recommend(){
  const pk=S.picks.length? Math.max(...S.picks.map(p=>p.pick))+1 : 1;
  const [,rnd]=slotOnClock(pk);
  const nx=nextOwn(pk+1), gap=nx?nx-pk:0;
  const c=counts(S.rosters[S.me]||[]);
  const q={}, out=[];
  for(const p of DATA.board){
    if(S.taken.has(p.i)) continue;
    q[p.p]=(q[p.p]||0)+1;
    const rate=(DATA.league[String(rnd)]||{})[p.p] || .25;
    const surv=poissonBelow(q[p.p], gap*rate);
    const [ok,note,kind]=allowed(p.p,rnd,c);
    const score=p.v + Math.max(0,p.v)*(1-surv)*.5 - (ok?0:1e6);
    out.push({...p,ok,note,kind,surv:Math.round(surv*100),score});
    if(out.length>300) break;
  }
  out.sort((a,b)=>b.score-a.score);
  const ok=out.filter(x=>x.ok).slice(0,6), no=out.filter(x=>!x.ok).slice(0,2);
  if(ok.length){ const best=Math.max(...ok.map(x=>x.v));
    ok.forEach(x=>x.cost=Math.max(0,best-x.v)); }
  return {pk,rnd,gap,ok,no};
}
function botPick(mgr,rnd){
  const c=counts(S.rosters[mgr]||[]);
  const t=(DATA.tendencies[mgr]||{})[String(rnd)] || DATA.league[String(rnd)] || {};
  const opts=Object.entries(t).filter(([k,v])=>v>0 && (c[k]||0)<(BOT_CAPS[k]||99));
  let pos=null;
  if(opts.length){
    const tot=opts.reduce((s,[,v])=>s+v,0); let r=Math.random()*tot;
    for(const [k,v] of opts){ r-=v; if(r<=0){ pos=k; break; } }
    if(!pos) pos=opts[opts.length-1][0];
  }
  let pick=DATA.board.find(p=>!S.taken.has(p.i) && (!pos || p.p===pos));
  if(!pick) pick=DATA.board.find(p=>!S.taken.has(p.i));
  return pick;
}
function record(pk,player,mgr){
  S.picks.push({pick:pk,mgr,...player});
  S.taken.add(player.i);
  (S.rosters[mgr]=S.rosters[mgr]||[]).push(player);
}
function runBots(){
  const total=DATA.teams*DATA.rounds;
  while(true){
    const pk=S.picks.length? Math.max(...S.picks.map(p=>p.pick))+1 : 1;
    if(pk>total){ S.done=true; break; }
    const [slot,rnd]=slotOnClock(pk);
    if(slot===S.slot) break;
    const mgr=DATA.managers[slot-1];
    const p=botPick(mgr,rnd);
    if(!p){ S.done=true; break; }
    record(pk,p,mgr);
  }
  render();
}
function take(id){
  const p=DATA.board.find(x=>x.i===id);
  if(!p || S.taken.has(id)) return;
  const pk=S.picks.length? Math.max(...S.picks.map(x=>x.pick))+1 : 1;
  record(pk,p,S.me);
  runBots();
}
function autoPick(){ const r=recommend(); if(r.ok.length) take(r.ok[0].i); }

function boardHTML(){
  const byPick={}; S.picks.forEach(p=>byPick[p.pick]=p);
  let h='<div class="board"><table><tr><th></th>';
  for(let i=0;i<DATA.teams;i++)
    h+='<th class="'+(i+1===S.slot?'me':'')+'">'+esc(DATA.managers[i].slice(0,13))+'</th>';
  h+='</tr>';
  for(let r=1;r<=DATA.rounds;r++){
    h+='<tr><td class="rd">'+r+'</td>';
    for(let s=1;s<=DATA.teams;s++){
      const off = r%2===1 ? s : DATA.teams-s+1;
      const pk=(r-1)*DATA.teams+off, p=byPick[pk];
      h+='<td><div class="cell '+(p?'c'+p.p:'empty')+(s===S.slot?' mine':'')+'">'+
        (p? '<span class="n">'+esc(p.n)+'</span><span class="p">'+p.p+'</span>'
          : '<span class="p">'+pk+'</span>')+'</div></td>';
    }
    h+='</tr>';
  }
  return h+'</table></div>';
}
function poolHTML(live){
  const seen={};
  return '<div class="pool">'+POS.map(pos=>{
    const list=DATA.board.filter(p=>p.p===pos && !S.taken.has(p.i)).slice(0,8);
    if(!list.length) return '';
    return '<div><h3>'+pos+'</h3>'+list.map(a=>
      '<div class="av c'+pos+'"'+(live?' data-act="take" data-arg="'+esc(a.i)+'"':'')+'>'+
      '<span>'+esc(a.n)+'</span><span class="v">'+a.v.toFixed(0)+'</span></div>').join('')+'</div>';
  }).join('')+'</div>';
}
function fillSlots(roster){
  // Assign what you have drafted to starting slots, most restrictive first.
  // Every flex accepts a superset of some dedicated slot, so that order gives
  // the true best arrangement rather than an approximation.
  const order=DATA.slots.map((s,i)=>[i,s])
    .sort((a,b)=>(DATA.eligible[a[1]]||[]).length-(DATA.eligible[b[1]]||[]).length);
  const used=new Set(), out=DATA.slots.map(s=>({slot:s,p:null}));
  for(const [i,s] of order){
    const elig=DATA.eligible[s]||[];
    let best=null;
    for(const p of roster){
      if(used.has(p.i) || !elig.includes(p.p)) continue;
      if(!best || p.v>best.v) best=p;
    }
    if(best){ used.add(best.i); out[i].p=best; }
  }
  return {lineup:out, bench:roster.filter(p=>!used.has(p.i))};
}
function rosterPanel(){
  const mine=S.rosters[S.me]||[];
  const {lineup,bench}=fillSlots(mine);
  const c=counts(mine);
  const holes=lineup.filter(x=>!x.p).length;
  return '<h2>Your roster</h2>'+
    '<div class="dens">'+POS.map(p=>'<span class="d c'+p+'">'+p+
      ' <b>'+(c[p]||0)+'</b></span>').join('')+'</div>'+
    '<table class="ros">'+lineup.map(x=>
      '<tr class="'+(x.p?'':'hole')+'"><td class="sl">'+x.slot+'</td><td>'+
      (x.p? '<span class="c'+x.p.p+' pill">'+x.p.p+'</span> '+esc(x.p.n)
          : '<span class="note">empty</span>')+'</td>'+
      '<td class="num">'+(x.p?x.p.j.toFixed(0):'')+'</td></tr>').join('')+'</table>'+
    (holes? '<p class="note">'+holes+' starting spot'+(holes>1?'s':'')+' still open</p>'
          : '<p class="note" style="color:var(--good)">Every starting spot filled</p>')+
    (bench.length? '<h3 style="margin-top:12px">Bench ('+bench.length+')</h3>'+
      '<table class="ros">'+bench.map(p=>'<tr><td class="sl">BN</td><td>'+
      '<span class="c'+p.p+' pill">'+p.p+'</span> '+esc(p.n)+'</td>'+
      '<td class="num">'+p.j.toFixed(0)+'</td></tr>').join('')+'</table>' : '');
}
function legend(){
  return '<details class="key"><summary>What the numbers mean</summary>'+
    '<table class="sum" style="margin-top:10px">'+
    '<tr><td><b>VOR</b></td><td>Value over replacement: how many more points this '+
      'player is projected to score than a player at his position you could pick up '+
      'off waivers for nothing. It is the honest way to compare a quarterback to a '+
      'running back &mdash; raw projected points are not comparable across positions, '+
      'because quarterbacks score more than everyone.</td></tr>'+
    '<tr><td><b>costs</b></td><td>What you give up by taking this row instead of the '+
      'most valuable player available. <b>costs 0</b> (shown as "best") means nothing '+
      'on the board beats him. This is the number that stops you reaching.</td></tr>'+
    '<tr><td><b>#</b></td><td>His rank on the whole board by VOR. Rank 40 taken at '+
      'pick 20 means you paid a round or two more than he is worth.</td></tr>'+
    '<tr><td><b>% back</b></td><td>The chance he is still on the board when your next '+
      'turn comes round. <b>5% back</b> means take him now or lose him; <b>60% back</b> '+
      'means you can probably grab someone else first and still get him. This is the '+
      'tiebreak when two players are close in value.</td></tr>'+
    '<tr><td><b>Greyed rows</b></td><td>Players your chosen strategy is blocking, and '+
      'why. They are shown rather than hidden so you can see what the rule is costing.</td></tr>'+
    '<tr><td><b>Red banner</b></td><td>Appears when your strategy is blocking someone '+
      'clearly better than anything it allows. Not an instruction &mdash; just the cost, '+
      'so you can break your own rule knowingly.</td></tr>'+
    '<tr><td><b>Colours</b></td><td>'+POS.map(p=>'<span class="c'+p+' pill">'+p+
      '</span>').join(' ')+' &mdash; position is always written out too, never colour alone.</td></tr>'+
    '</table></details>';
}
function summary(){
  const mine=S.rosters[S.me]||[];
  const c=counts(mine);
  const tot=mine.reduce((s,p)=>s+p.j,0);
  const firstQB=mine.findIndex(p=>p.p==="QB")+1;
  return '<h2>Your team</h2><table class="sum">'+mine.map((p,i)=>
    '<tr><td class="rd">R'+(i+1)+'</td><td><strong>'+esc(p.n)+'</strong></td>'+
    '<td>'+p.p+'</td><td>'+p.j.toFixed(1)+'</td>'+
    '<td>'+(p.v>=0?'+':'')+p.v.toFixed(0)+'</td></tr>').join('')+'</table>'+
    '<p class="sub" style="margin-top:10px">'+
    POS.filter(p=>c[p]).map(p=>p+' '+c[p]).join(' &middot; ')+
    ' &middot; projected total '+tot.toFixed(0)+
    (firstQB?' &middot; first QB round '+firstQB:'')+'</p>';
}

function render(){
  const app=document.getElementById("app");
  if(!S){ return renderSetup(); }
  if(S.done){
    app.className="wrap";
    app.innerHTML='<h1>Draft complete</h1><p class="sub">'+esc(S.me)+
      ' &middot; slot '+S.slot+' &middot; '+PRESETS[S.preset].label+'</p>'+
      summary()+'<h2>Draft board</h2>'+boardHTML()+
      '<p style="margin-top:20px"><button class="primary" data-act="reset">Run another</button></p>';
    return;
  }
  const r=recommend();
  const [slot]=slotOnClock(r.pk);
  const live=slot===S.slot;
  app.className="wrap"+(live?" live":"");
  const onClock=DATA.managers[slot-1];
  const warn=(()=>{
    const t=r.no.filter(x=>x.kind==="timing");
    if(!r.ok.length||!t.length) return "";
    const g=t[0].v-Math.max(...r.ok.map(x=>x.v));
    return g>=25 ? "Your strategy is expensive here: "+t[0].n+" ("+t[0].p+") is worth "+
      g.toFixed(0)+" more points, but "+t[0].note : "";
  })();
  app.innerHTML=
    '<h1>Mock draft room</h1><p class="sub">'+esc(S.me)+' &middot; slot '+S.slot+
      ' &middot; round '+r.rnd+', pick '+r.pk+' &middot; '+PRESETS[S.preset].label+'</p>'+
    (warn?'<div class="warn">'+esc(warn)+'</div>':'')+
    (live?'<div class="turn">YOUR PICK &mdash; click a player to draft him</div>'
        :'<div class="wait">'+esc(onClock)+' is picking&hellip;</div>')+
    '<div class="grid2"><div><h2>Take one of these</h2>'+
      r.ok.map((x,i)=>'<div class="rec'+(i===0?' top':'')+'"'+
        (live?' data-act="take" data-arg="'+esc(x.i)+'"':'')+'>'+
        '<span class="ps">'+x.p+'</span><span class="nm">'+esc(x.n)+'</span>'+
        '<span class="num">VOR '+x.v.toFixed(0)+'</span>'+
        '<span class="num">'+(x.cost>0?'costs '+x.cost.toFixed(0):'best')+'</span>'+
        '<span class="num">#'+x.r+'</span>'+
        '<span class="num">'+x.surv+'% back</span></div>').join('')+
      r.no.map(x=>'<div class="blocked">'+esc(x.n)+' ('+x.p+') &mdash; '+esc(x.note)+'</div>').join('')+
      '<p style="margin-top:12px"><button data-act="auto">Take the top one for me</button> '+
      '<button data-act="reset">Start over</button></p></div>'+
    '<div>'+rosterPanel()+'<h2>Recent picks</h2>'+
      S.picks.slice(-8).reverse().map(p=>'<div class="blocked">'+p.pick+'. '+
        esc(p.mgr)+' &mdash; '+esc(p.n)+' ('+p.p+')</div>').join('')+
    '</div></div>'+
    legend()+
    '<h2>Best available</h2>'+poolHTML(live)+
    '<h2>Draft board</h2>'+boardHTML();
}

let pick_me=null, pick_slot=null, pick_preset="value";
function renderSetup(){
  const app=document.getElementById("app");
  app.className="wrap";
  app.innerHTML='<h1>Mock draft room</h1>'+
    '<p class="sub">A practice draft against this league, using '+DATA.season+
    ' projections. The other eleven seats are filled by models of how those '+
    'managers have actually drafted &mdash; not generic bots.</p>'+
    '<div class="card"><h3>1. Which manager are you?</h3><div class="row">'+
      DATA.managers.map(m=>'<button data-m="'+esc(m)+'" data-act="me"'+
        (m===pick_me?' class="sel"':'')+'>'+esc(m)+'</button>').join('')+
    '</div></div>'+
    '<div class="card"><h3>2. Which draft slot?</h3><div class="row">'+
      Array.from({length:DATA.teams},(_,i)=>'<button data-act="slot" data-arg="'+(i+1)+'"'+
        (pick_slot===i+1?' class="sel"':'')+'>'+(i+1)+'</button>').join('')+
      '</div><p class="note">The real order is not out yet &mdash; pick any seat to practise.</p></div>'+
    '<div class="card"><h3>3. Strategy</h3><div class="row">'+
      Object.entries(PRESETS).map(([k,v])=>'<button data-act="preset" data-arg="'+k+'"'+
        (pick_preset===k?' class="sel"':'')+'>'+v.label+'</button>').join('')+
      '</div><p class="note">'+esc(PRESETS[pick_preset].note)+'</p></div>'+
    '<p style="margin-top:18px"><button class="primary" data-act="start"'+
      ((pick_me&&pick_slot)?'':' disabled')+'>Start drafting</button></p>'+
    '<p class="note">Nothing is sent anywhere. The whole draft runs in your browser.</p>';
}
function setMe(v){ pick_me=v; renderSetup(); }
function setSlot(n){ pick_slot=n; renderSetup(); }
function setPreset(k){ pick_preset=k; renderSetup(); }
function reset(){ S=null; renderSetup(); }
function start(){
  if(!pick_me||!pick_slot) return;
  const order=DATA.managers.slice();
  const here=order.indexOf(pick_me);
  if(here>=0){ const t=order[pick_slot-1]; order[pick_slot-1]=pick_me; order[here]=t; }
  DATA.managers=order;
  S={me:pick_me,slot:pick_slot,preset:pick_preset,picks:[],taken:new Set(),
     rosters:{},done:false};
  runBots();
}
// One delegated listener for the whole app, re-bound to nothing on re-render
// because it lives on the container rather than on the buttons themselves.
document.getElementById("app").addEventListener("click", function(ev){
  var el = ev.target && ev.target.closest ? ev.target.closest("[data-act]") : null;
  if(!el) return;
  var a = el.getAttribute("data-act"), v = el.getAttribute("data-arg");
  try{
    if(a==="me") setMe(el.getAttribute("data-m"));
    else if(a==="slot") setSlot(parseInt(v,10));
    else if(a==="preset") setPreset(v);
    else if(a==="start") start();
    else if(a==="take") take(v);
    else if(a==="auto") autoPick();
    else if(a==="reset") reset();
  }catch(err){ fail(err); }
});
renderSetup();
}catch(err){ fail(err); }
})();
</script>"""


def main():
    data = collect()
    blob = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    # ensure_ascii keeps the payload pure ASCII using \uXXXX escapes, which are
    # valid JavaScript. HTML entities would NOT work here -- they are not parsed
    # inside a <script> block.
    doc = PAGE.replace("__DATA__", blob)
    if any(ord(c) > 127 for c in doc):
        raise SystemExit("non-ASCII leaked into the page")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(doc, encoding="ascii")
    print(f"wrote {OUT}  ({len(doc)/1024:.0f} KB, {len(data['board'])} players, "
          f"{len(data['managers'])} managers)")


if __name__ == "__main__":
    main()
