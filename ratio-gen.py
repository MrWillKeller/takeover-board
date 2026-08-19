#!/usr/bin/env python3
"""ratio-gen.py — renders the Scout CCU/visits leaderboard as one self-contained HTML file.

Reads the newest FULL scrape-history snapshot (charts-only runs carry an empty
rotrends pool) and emits ratio.html. No network, no external assets.

ratio == ccu / visits, lifetime cumulative visits — the same formula Scout
computes at rotrends-scan.js:222. Not per-day, not log-scaled.
"""
import glob
import html
import json
import os
import sys

HIST = os.path.expanduser("~/.openclaw/shared/scrape-history")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.openclaw/shared/gemhunt-dash/ratio.html")

CSS = """
:root{--bg:#fbfbfa;--fg:#1a1a18;--dim:#6b6b66;--line:#e4e4e0;--card:#fff;--accent:#b4531f;--band:#fdf4e8}
@media(prefers-color-scheme:dark){:root{--bg:#151513;--fg:#ecebe6;--dim:#918f88;--line:#2c2c28;--card:#1d1d1a;--accent:#e08a4c;--band:#2a2118}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Inter,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:19px;margin:0 0 2px;letter-spacing:-.01em}
.sub{color:var(--dim);font-size:13px;margin-bottom:20px}
.nav{display:flex;gap:14px;margin-bottom:18px;font-size:13px}
.nav a{color:var(--dim);text-decoration:none;padding-bottom:3px;border-bottom:2px solid transparent}
.nav a:hover{color:var(--fg)}
.nav a.on{color:var(--fg);border-bottom-color:var(--accent)}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:9px 14px;min-width:96px}
.stat b{display:block;font-size:20px;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.stat span{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
.warn{background:var(--band);border:1px solid var(--line);border-left:3px solid var(--accent);
      border-radius:7px;padding:11px 14px;margin-bottom:18px;font-size:13px;color:var(--fg)}
.tools{display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
input,select{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:7px;
             padding:7px 10px;font:inherit;font-size:13px}
input[type=text]{flex:1;min-width:170px}
.tblwrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th{position:sticky;top:0;background:var(--card);text-align:right;font-size:11px;color:var(--dim);
   text-transform:uppercase;letter-spacing:.05em;padding:10px 12px;cursor:pointer;white-space:nowrap;
   border-bottom:1px solid var(--line);user-select:none}
th:first-child,td:first-child{text-align:left}
th:hover{color:var(--fg)}
th.on{color:var(--accent)}
td{padding:9px 12px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
tr:last-child td{border-bottom:0}
tr.hide{display:none}
a{color:inherit;text-decoration:none;font-weight:500}
a:hover{color:var(--accent);text-decoration:underline}
.mut{color:var(--dim)}
.legend{margin-top:22px;color:var(--dim);font-size:12.5px;line-height:1.75;max-width:760px}
.legend b{color:var(--fg)}
"""

JS = """
var sk="ratio",sd=-1;
function fmt(n){if(n===null||n===undefined)return'<span class="mut">-</span>';
  if(n>=1e9)return (n/1e9).toFixed(1)+'B';if(n>=1e6)return (n/1e6).toFixed(1)+'M';
  if(n>=1e3)return (n/1e3).toFixed(1)+'K';return String(n);}
function draw(){
  var q=document.getElementById('q').value.toLowerCase();
  var mc=parseInt(document.getElementById('minccu').value,10);
  var rows=G.filter(function(g){
    if(mc&&(g.ccu||0)<mc)return false;
    if(q&&(g.name||'').toLowerCase().indexOf(q)<0&&(g.dev||'').toLowerCase().indexOf(q)<0)return false;
    return true;});
  rows.sort(function(a,b){var x=a[sk],y=b[sk];
    if(x===null||x===undefined)return 1;if(y===null||y===undefined)return -1;
    if(typeof x==='string')return sd*x.localeCompare(y);return sd*(x-y)>0?1:-1;});
  document.getElementById('shown').innerHTML='<b>'+rows.length+'</b><span>shown</span>';
  var h='';
  for(var i=0;i<rows.length;i++){var g=rows[i];
    h+='<tr><td><a href="'+g.url+'" target="_blank" rel="noopener">'+g.name+'</a></td>'
      +'<td>'+(g.ratio!==null?g.ratio.toFixed(6):'<span class="mut">-</span>')+'</td>'
      +'<td>'+fmt(g.ccu)+'</td><td>'+fmt(g.visits)+'</td>'
      +'<td>'+(g.play!==null?g.play.toFixed(1):'<span class="mut">-</span>')+'</td>'
      +'<td>'+(g.like!==null?g.like.toFixed(1)+'%':'<span class="mut">-</span>')+'</td>'
      +'<td class="mut">'+(g.rel||'-')+'</td>'
      +'<td class="mut">'+(g.dev||'-')+'</td></tr>';}
  document.getElementById('tb').innerHTML=h;
  var ths=document.querySelectorAll('th[data-k]');
  for(var j=0;j<ths.length;j++)ths[j].className=(ths[j].dataset.k===sk?'on':'');
}
document.querySelectorAll('th[data-k]').forEach(function(th){th.onclick=function(){
  var k=th.dataset.k;if(k===sk)sd=-sd;else{sk=k;sd=(k==='name'||k==='dev')?1:-1;}draw();};});
document.getElementById('q').oninput=draw;
document.getElementById('minccu').onchange=draw;
draw();
"""


def newest_full():
    files = [f for f in glob.glob(os.path.join(HIST, "2026-*.json")) if "-chr" not in f]
    for f in sorted(files, reverse=True):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        if d.get("rotrends"):
            return f, d
    return None, None


def main():
    path, d = newest_full()
    if not d:
        sys.exit("no full snapshot with a rotrends pool found in %s" % HIST)

    games = []
    for g in d["rotrends"]:
        if not g.get("url"):
            continue
        games.append({
            "name": g.get("name") or "?",
            "url": g.get("url"),
            "ratio": g.get("ratio"),
            "ccu": g.get("ccu"),
            "visits": g.get("visits"),
            # rotrends' own derived session estimate, parsed from their table
            "play": g.get("playtimeMin"),
            "like": g.get("likePct"),
            "rel": g.get("released"),
            "dev": g.get("developer"),
        })
    games.sort(key=lambda g: (g["ratio"] is None, -(g["ratio"] or 0)))

    withratio = sum(1 for g in games if g["ratio"] is not None)
    ts = d.get("timestamp", "")

    cols = [("name", "game"), ("ratio", "ccu/visits"), ("ccu", "ccu"), ("visits", "visits"),
            ("play", "session"), ("like", "like %"), ("rel", "released"), ("dev", "developer")]
    thead = "".join('<th data-k="%s"%s>%s</th>' % (k, ' class="on"' if k == "ratio" else "", lbl)
                    for k, lbl in cols)

    doc = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>CCU / visits leaderboard</title><style>%s</style></head><body><div class="wrap">
<h1>CCU / visits leaderboard</h1>
<div class="sub">Scout rotrends pool &middot; snapshot %s</div>
<div class="nav"><a href="./">overview</a><a href="gemhunt.html">gemhunt board</a><a class="on" href="ratio.html">ccu / visits</a></div>
<div class="stats">
  <div class="stat"><b>%d</b><span>games</span></div>
  <div class="stat"><b>%d</b><span>with ratio</span></div>
  <div class="stat" id="shown"><b>-</b><span>shown</span></div>
</div>
<div class="warn"><b>Read this before ranking on it.</b> The ratio is live CCU divided by
<b>lifetime cumulative visits</b>, so a brand-new game with few total visits sits at the top by
construction &mdash; it is a &ldquo;busy relative to how long it has existed&rdquo; measure, not a quality score.
Raise the min-CCU filter to compare games at a comparable size. Visits come from rotrends and are
rounded to 3 significant figures, so the denominator is coarse for large games.</div>
<div class="tools">
  <input type="text" id="q" placeholder="filter by game or developer&hellip;">
  <select id="minccu">
    <option value="0">any CCU</option><option value="100" selected>CCU &ge; 100</option>
    <option value="500">CCU &ge; 500</option><option value="1000">CCU &ge; 1,000</option>
    <option value="10000">CCU &ge; 10,000</option>
  </select>
</div>
<div class="tblwrap"><table><thead><tr>%s</tr></thead><tbody id="tb"></tbody></table></div>
<div class="legend"><b>ccu/visits</b> &mdash; concurrent players divided by lifetime visits.
<b>session</b> &mdash; rotrends' own playtime estimate in minutes, shown as published, not recomputed.
<b>like %%</b> &mdash; rotrends like ratio. Click any column to sort. Rows link out to roblox.com.</div>
</div><script>const G=%s;\n%s</script></body></html>
""" % (CSS, html.escape(ts), len(games), withratio, thead,
       json.dumps(games, separators=(",", ":"), ensure_ascii=False), JS)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        f.write(doc)
    os.replace(tmp, OUT)
    print("wrote %s (%d bytes) from %s — %d games, %d with ratio"
          % (OUT, os.path.getsize(OUT), os.path.basename(path), len(games), withratio))


if __name__ == "__main__":
    main()
