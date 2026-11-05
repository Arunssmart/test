"""Scan a photo folder: read dates and camera data, score sharpness and exposure,
make thumbnails, and group near-identical shots (bursts) so only the best frame
of each needs a look."""

import datetime as dt
import hashlib
import multiprocessing as mp
import os
import time
from collections import Counter, defaultdict

import cv2
import numpy as np

from . import common

THUMB_SIDE = 480
ANALYSIS_SIDE = 1024
GRID = 4  # sharpness is measured per tile on a GRID x GRID grid
SCAN_VERSION = 2  # bump when the per-photo analysis changes, so old results are redone


def _dhash(gray_img):
    small = np.asarray(gray_img.resize((9, 8)), dtype=np.int16)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def analyze_one(job):
    path, rel, kind, size, mtime, thumb_dir = job
    rec = {"rel": rel, "kind": kind, "bytes": size, "mtime": mtime, "v": SCAN_VERSION}
    try:
        im, (w, h), meta = common.open_preview(path, kind, max_side=1600)
        rec.update(width=w, height=h)
        taken = meta.pop("taken", None)
        rec["exif_taken"] = taken.isoformat() if taken else None
        rec["exif_date_source"] = meta.pop("date_source", None)
        meta.pop("orientation", None)
        rec.update(meta)

        thumb_name = hashlib.sha1(rel.encode()).hexdigest()[:16] + ".jpg"
        t = im.copy()
        t.thumbnail((THUMB_SIDE, THUMB_SIDE))
        t.save(os.path.join(thumb_dir, thumb_name), quality=85)
        rec["thumb"] = thumb_name

        a = im.copy()
        a.thumbnail((ANALYSIS_SIDE, ANALYSIS_SIDE))
        arr = np.asarray(a, dtype=np.float32) / 255.0
        y = arr @ common.LUMA
        # Sharpness: variance of the Laplacian, per tile. The best tile tells us
        # whether the subject is sharp even when the background is soft.
        g = cv2.GaussianBlur(y * 255.0, (0, 0), 0.8)
        lap = cv2.Laplacian(g, cv2.CV_32F, ksize=3)
        H, W = lap.shape
        tiles = []
        for r in range(GRID):
            for c in range(GRID):
                tile = lap[r * H // GRID:(r + 1) * H // GRID, c * W // GRID:(c + 1) * W // GRID]
                tiles.append(float(tile.var()))
        best = int(np.argmax(tiles))
        rec["sharp_max"] = round(max(tiles), 1)
        rec["sharp_med"] = round(float(np.median(tiles)), 1)
        rec["sharp_tile"] = [best // GRID, best % GRID]
        rec["sharp_global"] = round(float(lap.var()), 1)

        mx = arr.max(axis=2)
        rec["lum_p01"] = round(float(np.percentile(y, 1)), 3)
        rec["lum_med"] = round(float(np.median(y)), 3)
        rec["lum_p99"] = round(float(np.percentile(y, 99)), 3)
        rec["clip_hi"] = round(float((mx >= 0.985).mean()), 3)
        rec["clip_lo"] = round(float((y <= 0.02).mean()), 3)
        rec["dhash"] = format(_dhash(a.convert("L")), "016x")
        rec["status"] = "ok"
    except Exception as e:  # keep going; report at the end
        rec["status"] = "error"
        rec["error"] = f"{type(e).__name__}: {e}"[:300]
    return rec


def _assign_dates(recs):
    for r in recs:
        if r.get("status") != "ok":
            continue
        taken, src = None, None
        if r.get("exif_taken"):
            taken, src = dt.datetime.fromisoformat(r["exif_taken"]), r.get("exif_date_source") or "camera"
        if taken is None:
            taken = common.date_from_name(os.path.basename(r["rel"]))
            src = "filename" if taken else None
        if taken is None:
            taken, src = dt.datetime.fromtimestamp(r["mtime"]), "file-modified"
        r["taken"] = taken.isoformat(timespec="seconds" if taken.microsecond == 0 else "milliseconds")
        r["date"] = taken.date().isoformat()
        r["date_source"] = src


def _group(recs, burst_gap, burst_ham, similar_gap, similar_ham):
    """Assign ids, mark exact duplicates, and group bursts / near-identical shots."""
    by_date = defaultdict(list)
    for r in recs:
        if r.get("status") == "ok":
            by_date[r["date"]].append(r)
    for date, items in by_date.items():
        items.sort(key=lambda r: (r["taken"], r["rel"]))
        width = max(3, len(str(len(items))))
        for i, r in enumerate(items, 1):
            r["id"] = f"{date.replace('-', '')}-{i:0{width}d}"
            r["dup_of"] = None

        # exact copies: same moment, same size, (almost) same picture
        seen = {}
        for r in items:
            key = (r["taken"][:19], r["width"], r["height"])
            for o in seen.get(key, []):
                if hamming(o["dhash"], r["dhash"]) <= 3:
                    r["dup_of"] = o["id"]
                    break
            seen.setdefault(key, []).append(r)

        groups, cur, prev = [], [], None
        for r in items:
            if r["dup_of"]:
                continue
            t = dt.datetime.fromisoformat(r["taken"])
            if prev is not None:
                gap = (t - prev[1]).total_seconds()
                ham = hamming(prev[0]["dhash"], r["dhash"])
                same = (gap <= burst_gap and ham <= burst_ham) or (gap <= similar_gap and ham <= similar_ham)
                if not same or r["date_source"] == "file-modified":
                    groups.append(cur)
                    cur = []
            cur.append(r)
            prev = (r, t)
        if cur:
            groups.append(cur)

        for gi, g in enumerate(groups, 1):
            gid = f"{date.replace('-', '')}-g{gi:03d}"

            def score(r):
                s = r["sharp_max"]
                if r["clip_hi"] > 0.15 or r["lum_med"] < 0.06:
                    s *= 0.6
                return s

            best = max(g, key=score)
            for r in g:
                r["group"] = gid
                r["group_size"] = len(g)
                r["group_best"] = r is best
                r["soft_vs_group"] = len(g) > 1 and r["sharp_max"] < 0.35 * best["sharp_max"]
        for r in items:
            if r["dup_of"]:
                r["group"], r["group_size"], r["group_best"], r["soft_vs_group"] = None, 0, False, False


def _flags(r, blur_threshold):
    f = []
    if r.get("dup_of"):
        f.append("copy")
    if r["sharp_max"] < blur_threshold or r.get("soft_vs_group"):
        f.append("soft")
    if r["lum_med"] < 0.08 and r["lum_p99"] < 0.45:
        f.append("dark")
    if r["clip_hi"] > 0.2:
        f.append("bright")
    if r["date_source"] == "file-modified":
        f.append("no-date")
    return f


def run(src, work, out=None, workers=None, burst_gap=4.0, burst_ham=20, similar_gap=60.0,
        similar_ham=10, blur_threshold=80.0, fresh=False):
    src = os.path.abspath(os.path.expanduser(src))
    work = os.path.abspath(os.path.expanduser(work))
    if not os.path.isdir(src):
        raise SystemExit(f"Photo folder not found: {src}")
    thumb_dir = os.path.join(work, "thumbs")
    os.makedirs(thumb_dir, exist_ok=True)
    common.mark_folder(work, ".wildlife-kit-work", "Wildlife Photo Kit working files (thumbnails, lists).")
    exclude = [work] + ([os.path.abspath(os.path.expanduser(out))] if out else [])
    kit_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    exclude.append(kit_dir)

    print(f"Looking for photos in {src} ...", flush=True)
    files, skipped = common.find_photos(src, exclude)
    print(f"Found {len(files)} photos.", flush=True)

    # Reuse results from an earlier (possibly interrupted) scan for unchanged files.
    prev = {}
    for name in ("catalog.json", "catalog.partial.json"):
        p = os.path.join(work, name)
        if os.path.exists(p):
            try:
                import json

                with open(p) as f:
                    data = json.load(f)
                if data.get("src") == src:
                    for r in data["photos"]:
                        prev[r["rel"]] = r
            except Exception:
                pass

    jobs, done = [], []
    for full, rel, kind in files:
        st = os.stat(full)
        old = prev.get(rel)
        if (not fresh and old and old.get("status") == "ok" and old.get("v") == SCAN_VERSION
                and old.get("bytes") == st.st_size
                and abs(old.get("mtime", 0) - st.st_mtime) < 1
                and os.path.exists(os.path.join(thumb_dir, old.get("thumb", "")))):
            done.append(old)
        else:
            jobs.append((full, rel, kind, st.st_size, st.st_mtime, thumb_dir))
    if done:
        print(f"Reusing {len(done)} photos from the previous scan; {len(jobs)} to scan.", flush=True)

    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    t0 = time.time()
    if jobs:
        ctx = mp.get_context("spawn")
        with ctx.Pool(workers) as pool:
            for i, rec in enumerate(pool.imap_unordered(analyze_one, jobs, chunksize=4), 1):
                done.append(rec)
                if i % 100 == 0 or i == len(jobs):
                    rate = i / max(time.time() - t0, 1e-6)
                    left = (len(jobs) - i) / max(rate, 1e-6)
                    print(f"  scanned {i}/{len(jobs)}  (~{left / 60:.0f} min left)", flush=True)
                if i % 500 == 0:
                    common.write_json(os.path.join(work, "catalog.partial.json"),
                                      {"src": src, "photos": done})

    _assign_dates(done)
    _group(done, burst_gap, burst_ham, similar_gap, similar_ham)
    for r in done:
        if r.get("status") == "ok":
            r["flags"] = _flags(r, blur_threshold)
            r["path"] = os.path.join(src, r["rel"])
    done.sort(key=lambda r: (r.get("taken") or "9999", r["rel"]))

    catalog = {
        "src": src,
        "scanned_at": dt.datetime.now().isoformat(timespec="seconds"),
        "settings": {"burst_gap": burst_gap, "burst_ham": burst_ham, "similar_gap": similar_gap,
                     "similar_ham": similar_ham, "blur_threshold": blur_threshold},
        "skipped": skipped,
        "photos": done,
    }
    common.write_json(os.path.join(work, "catalog.json"), catalog)
    p = os.path.join(work, "catalog.partial.json")
    if os.path.exists(p):
        os.remove(p)
    _write_csv(work, done)
    summary = _summary(catalog)
    with open(os.path.join(work, "summary.md"), "w") as f:
        f.write(summary)
    print()
    print(summary)


def _write_csv(work, recs):
    import csv

    cols = ["id", "date", "taken", "date_source", "rel", "width", "height", "camera", "lens",
            "focal_mm", "fnumber", "exposure_s", "iso", "gps", "sharp_max", "lum_med", "clip_hi",
            "group", "group_size", "group_best", "dup_of", "flags", "status", "error"]
    with open(os.path.join(work, "catalog.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            row = dict(r)
            row["flags"] = " ".join(r.get("flags", []))
            w.writerow(row)


def _summary(cat):
    ok = [r for r in cat["photos"] if r.get("status") == "ok"]
    err = [r for r in cat["photos"] if r.get("status") != "ok"]
    years = Counter(r["date"][:4] for r in ok)
    dates = Counter(r["date"] for r in ok)
    srcs = Counter(r["date_source"] for r in ok)
    review = [r for r in ok if r.get("group_best")]
    dups = [r for r in ok if r.get("dup_of")]
    lines = ["# Scan summary", "", f"Photo folder: `{cat['src']}`", f"Scanned: {cat['scanned_at']}", "",
             f"- Photos read: **{len(ok)}**",
             f"- Could not read: **{len(err)}**",
             f"- Exact copies found: {len(dups)}",
             f"- Groups of near-identical shots: {len(review)} (one best frame from each goes to review)",
             f"- Shooting days: {len(dates)}", "", "## Where each date came from", ""]
    names = {"camera": "camera (EXIF date taken)", "camera-modified": "camera/editor timestamp",
             "filename": "file name", "file-modified": "file modified date (least reliable)"}
    for k, v in srcs.most_common():
        lines.append(f"- {names.get(k, k)}: {v}")
    lines += ["", "## Photos per year", "", "| Year | Photos | Days |", "|---|---|---|"]
    for y in sorted(years):
        lines.append(f"| {y} | {years[y]} | {len([d for d in dates if d.startswith(y)])} |")
    lines += ["", "## Busiest days", ""]
    for d, n in dates.most_common(15):
        lines.append(f"- {d}: {n}")
    sk = cat.get("skipped", {})
    notes = []
    if sk.get("raw_no_decoder"):
        notes.append(f"{sk['raw_no_decoder']} RAW files skipped (install rawpy to include them)")
    if sk.get("heif_no_decoder"):
        notes.append(f"{sk['heif_no_decoder']} HEIC files skipped (install pillow-heif to include them)")
    if sk.get("library_packages"):
        notes.append("Skipped photo library packages: " + ", ".join(sk["library_packages"]))
    if sk.get("unsupported"):
        notes.append(f"{sk['unsupported']} non-photo files ignored")
    if notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    if err:
        lines += ["", "## Could not read", ""] + [f"- `{r['rel']}`: {r.get('error')}" for r in err[:50]]
        if len(err) > 50:
            lines.append(f"- ... and {len(err) - 50} more (see catalog.csv)")
    return "\n".join(lines) + "\n"
