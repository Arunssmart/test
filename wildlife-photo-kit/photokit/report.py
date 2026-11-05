"""A simple gallery page (index.html) of the edited photos, grouped by year and date,
with any post drafts shown alongside. Opens in any browser; works offline."""

import csv
import glob
import html
import os
from collections import defaultdict

from . import common, instagram

CSS = """
:root { --bg:#f6f5f2; --fg:#1d1d1b; --muted:#6b6a66; --card:#ffffff; --line:#e3e1dc; --accent:#3d6b4f; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#151514; --fg:#ecebe8; --muted:#a3a19b; --card:#1f1f1d; --line:#2f2e2b; --accent:#8fc3a0; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font:16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
header { padding:40px 24px 16px; max-width:1200px; margin:0 auto; }
h1 { margin:0 0 6px; font-size:30px; letter-spacing:-0.01em; }
.sub { color:var(--muted); }
nav { max-width:1200px; margin:0 auto; padding:0 24px 8px; display:flex; flex-wrap:wrap; gap:8px; }
nav a { color:var(--accent); text-decoration:none; border:1px solid var(--line); border-radius:999px;
        padding:2px 12px; font-size:14px; }
main { max-width:1200px; margin:0 auto; padding:0 24px 60px; }
h2 { margin:40px 0 4px; font-size:24px; border-bottom:1px solid var(--line); padding-bottom:6px; }
h3 { margin:26px 0 10px; font-size:17px; }
h3 small { color:var(--muted); font-weight:normal; }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); gap:14px; }
figure { margin:0; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
figure img { display:block; width:100%; height:240px; object-fit:cover; background:#000; }
figcaption { padding:8px 12px 12px; font-size:14px; }
figcaption b { display:block; }
figcaption span { color:var(--muted); }
figcaption a { color:var(--accent); font-size:13px; }
.post { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 16px;
        margin:12px 0 0; white-space:pre-wrap; font-size:14px; }
.post-title { font-size:13px; color:var(--muted); margin:14px 0 0; }
.carousel { display:flex; gap:6px; overflow-x:auto; margin:8px 0 0; }
.carousel img { height:200px; border-radius:6px; border:1px solid var(--line); }
"""


def run(work, out, title="Wildlife picks"):
    out = os.path.abspath(os.path.expanduser(out))
    log_path = os.path.join(out, "edit_log.csv")
    if not os.path.exists(log_path):
        raise SystemExit("No edit_log.csv yet. Run the edit step first.")
    with open(log_path, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("status") == "ok"]
    cat = common.load_catalog(work)
    recs = common.by_id(cat)
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["date"]].append(r)
    years = sorted({d[:4] for d in by_date}, reverse=True)
    species = {r["species"] for r in rows if r.get("species")}

    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
             f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
             f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>",
             f"<header><h1>{html.escape(title)}</h1><div class='sub'>{len(rows)} photos · "
             f"{len(by_date)} days · {len(species)} species/subjects</div></header>",
             "<nav>" + "".join(f"<a href='#y{y}'>{y}</a>" for y in years) + "</nav><main>"]
    for y in years:
        parts.append(f"<h2 id='y{y}'>{y}</h2>")
        for d in sorted((d for d in by_date if d.startswith(y)), reverse=True):
            items = sorted(by_date[d], key=lambda r: r["id"])
            sp = sorted({r["species"] for r in items if r.get("species")})
            parts.append(f"<h3>{d} <small>{len(items)} photo{'s' if len(items) != 1 else ''}"
                         f"{' · ' + html.escape(', '.join(sp)) if sp else ''}</small></h3><div class='grid'>")
            for r in items:
                rec = recs.get(r["id"], {})
                shot = " · ".join(p for p in [
                    rec.get("camera") or "",
                    f"{rec['focal_mm']:.0f}mm" if rec.get("focal_mm") else "",
                    f"ISO {rec['iso']:.0f}" if rec.get("iso") else "",
                ] if p)
                social = r["social"].replace(os.sep, "/")
                full = r["edited"].replace(os.sep, "/")
                parts.append(
                    f"<figure><a href='{html.escape(full)}'><img loading='lazy' src='{html.escape(social)}' "
                    f"alt='{html.escape(r.get('species') or r['id'])}'></a><figcaption>"
                    f"<b>{html.escape(r.get('species') or 'Untitled')}</b>"
                    f"{('<div>' + html.escape(r['caption']) + '</div>') if r.get('caption') else ''}"
                    f"<span>{html.escape(r['id'])}{' · ' + html.escape(shot) if shot else ''}</span><br>"
                    f"<a href='{html.escape(full)}'>full size</a></figcaption></figure>")
            parts.append("</div>")
            for post in sorted(glob.glob(os.path.join(out, "Posts", f"{d}*.md"))):
                name = os.path.splitext(os.path.basename(post))[0]
                p = instagram.parse_post(post)
                ig = sorted(glob.glob(os.path.join(out, "Instagram", name, "*.jpg")))
                parts.append(f"<div class='post-title'>Instagram post · Posts/{html.escape(name)}.md"
                             f"{' · ready in Instagram/' + html.escape(name) if ig else ''}</div>")
                if ig:
                    parts.append("<div class='carousel'>" + "".join(
                        f"<img loading='lazy' src='{html.escape(os.path.relpath(x, out).replace(os.sep, '/'))}'>"
                        for x in ig) + "</div>")
                parts.append(f"<div class='post'>{html.escape(p['body'])}</div>")
    parts.append("</main></body></html>")
    path = os.path.join(out, "index.html")
    with open(path, "w") as f:
        f.write("".join(parts))
    print(f"Gallery written to {path}")
