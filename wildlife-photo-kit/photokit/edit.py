"""Automatic, natural-looking edits for chosen photos.

Each photo gets the adjustments a careful editor would make in Lightroom:
straighten and crop, white balance, exposure, highlights and shadows, contrast,
local contrast (clarity), vibrance, noise reduction and sharpening. Settings are
worked out from each photo and can be adjusted per photo in picks.csv.

Nothing is added to or removed from the scene."""

import csv
import hashlib
import json
import math
import os

import cv2
import numpy as np
from PIL import Image

from . import common

STYLES = {
    #            shadows highlights contrast clarity vibrance saturation sharpen
    "natural": dict(shadows=0.32, highlights=0.30, contrast=1.0, clarity=0.22, vibrance=0.22, saturation=0.00, sharpen=0.9),
    "vivid":   dict(shadows=0.35, highlights=0.35, contrast=1.4, clarity=0.35, vibrance=0.38, saturation=0.06, sharpen=1.0),
    "soft":    dict(shadows=0.30, highlights=0.30, contrast=0.6, clarity=0.08, vibrance=0.15, saturation=0.00, sharpen=0.7),
    "bw":      dict(shadows=0.30, highlights=0.30, contrast=1.5, clarity=0.35, vibrance=0.00, saturation=0.00, sharpen=1.0),
}

ASPECTS = {"orig": None, "": None, "3:2": 1.5, "2:3": 2 / 3, "4:3": 4 / 3, "3:4": 0.75, "16:9": 16 / 9,
           "9:16": 9 / 16, "5:4": 1.25, "4:5": 0.8, "1:1": 1.0, "2:1": 2.0, "3:1": 3.0}

PICK_COLUMNS = ["id", "species", "caption", "aspect", "cx", "cy", "zoom", "rotate", "ev", "warmth",
                "style", "notes"]


# ------------------------------------------------------------------ colour helpers

def srgb_to_linear(x):
    """sRGB (0..1) to linear light. Integer images use a lookup table (fast)."""
    if x.dtype == np.uint8:
        return LIN8[x]
    if x.dtype == np.uint16:
        return LIN16[x]
    x = np.clip(x, 0, 1).astype(np.float32)
    low = x <= 0.04045
    lowv = x[low] / 12.92
    x += 0.055
    x *= 1 / 1.055
    np.power(x, np.float32(2.4), out=x)
    x[low] = lowv
    return x


def linear_to_srgb(x, inplace=False):
    x = np.maximum(x, 0, out=x if inplace else None).astype(np.float32, copy=False)
    low = x <= 0.0031308
    lowv = x[low] * 12.92
    np.power(x, np.float32(1 / 2.4), out=x)
    x *= 1.055
    x -= 0.055
    x[low] = lowv
    return x


def _lut(n):
    v = np.arange(n, dtype=np.float64) / (n - 1)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4).astype(np.float32)


LIN8, LIN16 = _lut(256), _lut(65536)


def clamp(a, lo=0.0, hi=1.0):
    """In-place clamp; much faster than np.clip on big arrays."""
    np.maximum(a, lo, out=a)
    np.minimum(a, hi, out=a)
    return a


def chmax(rgb):
    return np.maximum(np.maximum(rgb[..., 0], rgb[..., 1]), rgb[..., 2])


def chmin(rgb):
    return np.minimum(np.minimum(rgb[..., 0], rgb[..., 1]), rgb[..., 2])


def luma(img):
    return img @ common.LUMA


def smoothstep(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


def fit_gamut(rgb, y):
    """Pull colours back inside 0..1 by reducing their saturation, keeping brightness and hue.
    Works in place, and only on the pixels that are out of range."""
    rgb = np.ascontiguousarray(rgb, dtype=np.float32)
    flat, yf = rgb.reshape(-1, 3), np.ascontiguousarray(y, dtype=np.float32).reshape(-1)
    idx = np.flatnonzero(chmax(rgb).reshape(-1) > 1.0)
    if idx.size:
        p, yy = flat[idx], yf[idx][:, None]
        m = p.max(axis=1, keepdims=True)
        flat[idx] = yy + (p - yy) * np.clip((1.0 - yy) / np.maximum(m - yy, 1e-6), 0, 1)
    idx = np.flatnonzero(chmin(rgb).reshape(-1) < 0.0)
    if idx.size:
        p, yy = flat[idx], yf[idx][:, None]
        m = p.min(axis=1, keepdims=True)
        flat[idx] = yy + (p - yy) * np.clip(yy / np.maximum(yy - m, 1e-6), 0, 1)
    clamp(rgb)
    return rgb


def fast_guided_base(y, scale_side=640, radius=10, eps=0.015):
    """Edge-aware smooth version of the brightness (a 'fast guided filter').

    Computed small for speed, then applied at full size so it follows edges
    in the full-resolution photo (no glow around the subject)."""
    H, W = y.shape
    s = scale_side / max(H, W)
    if s >= 1:
        ys = y
    else:
        ys = cv2.resize(y, (max(1, int(W * s)), max(1, int(H * s))), interpolation=cv2.INTER_AREA)
    k = (2 * radius + 1, 2 * radius + 1)

    def box(a):
        return cv2.boxFilter(a, -1, k, borderType=cv2.BORDER_REFLECT)

    m = box(ys)
    var = box(ys * ys) - m * m
    a = var / (var + eps)
    b = m - a * m
    a, b = box(a), box(b)
    if ys is not y:
        a = cv2.resize(a, (W, H), interpolation=cv2.INTER_LINEAR)
        b = cv2.resize(b, (W, H), interpolation=cv2.INTER_LINEAR)
    return clamp(a * y + b)


def blur_large(y, sigma):
    """Wide Gaussian blur, done at reduced size for speed."""
    H, W = y.shape
    f = max(1, int(sigma / 6))
    if f > 1:
        ys = cv2.resize(y, (max(1, W // f), max(1, H // f)), interpolation=cv2.INTER_AREA)
        ys = cv2.GaussianBlur(ys, (0, 0), sigma / f)
        return cv2.resize(ys, (W, H), interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(y, (0, 0), sigma)


def noise_sigma(y):
    """Rough noise level (in 0-255 units) from a centre crop, using Immerkaer's method."""
    H, W = y.shape
    c = y[H // 4:3 * H // 4, W // 4:3 * W // 4] * 255.0
    if c.shape[0] < 16 or c.shape[1] < 16:
        return 0.0
    kern = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    conv = np.abs(cv2.filter2D(c, -1, kern))[1:-1, 1:-1]
    # ignore strong edges so detail isn't mistaken for noise
    conv = conv[conv < np.percentile(conv, 90)]
    return float(math.sqrt(math.pi / 2) * conv.mean() / 6.0)


# ------------------------------------------------------------------ geometry

def rotate_and_trim(img, degrees):
    if not degrees:
        return img
    H, W = img.shape[:2]
    M = cv2.getRotationMatrix2D((W / 2, H / 2), degrees, 1.0)
    rot = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    a = math.radians(abs(degrees))
    sin_a, cos_a = math.sin(a), math.cos(a)
    long_side, short_side = max(W, H), min(W, H)
    if short_side <= 2 * sin_a * cos_a * long_side or abs(sin_a - cos_a) < 1e-10:
        x = 0.5 * short_side
        wr, hr = (x / sin_a, x / cos_a) if W >= H else (x / cos_a, x / sin_a)
    else:
        cos_2a = cos_a * cos_a - sin_a * sin_a
        wr, hr = (W * cos_a - H * sin_a) / cos_2a, (H * cos_a - W * sin_a) / cos_2a
    wr, hr = int(wr) - 2, int(hr) - 2
    x0, y0 = (W - wr) // 2, (H - hr) // 2
    return rot[y0:y0 + hr, x0:x0 + wr]


def crop_box(W, H, aspect, cx, cy, zoom):
    ratio = ASPECTS.get(str(aspect).strip(), None) if aspect is not None else None
    if ratio is None and str(aspect).strip() not in ASPECTS:
        try:
            a, b = str(aspect).split(":")
            ratio = float(a) / float(b)
        except Exception:
            ratio = None
    ratio = ratio or W / H
    if W / H > ratio:
        h0, w0 = H, H * ratio
    else:
        w0, h0 = W, W / ratio
    zoom = min(max(zoom, 0.1), 1.0)
    w, h = w0 * zoom, h0 * zoom
    x0 = min(max(cx * W - w / 2, 0), W - w)
    y0 = min(max(cy * H - h / 2, 0), H - h)
    return int(round(x0)), int(round(y0)), int(round(x0 + w)), int(round(y0 + h))


# ------------------------------------------------------------------ the edit

def _f(v, default):
    try:
        return float(v) if str(v).strip() != "" else default
    except ValueError:
        return default


def develop(img, iso=None, style="natural", ev=0.0, warmth=0.0, report=None):
    """Return the edited image (float32 sRGB 0..1). `report` collects the settings used."""
    st = dict(STYLES.get(style, STYLES["natural"]))
    rep = report if report is not None else {}
    warnings = []
    H, W = img.shape[:2]
    small = cv2.resize(img, (max(1, int(W * 800 / max(H, W))), max(1, int(H * 800 / max(H, W)))),
                       interpolation=cv2.INTER_AREA) if max(H, W) > 800 else img.copy()
    small = common.to_float(small)

    # 1. white balance (conservative: only corrects casts seen in near-neutral areas)
    sl = srgb_to_linear(small)
    mx, mn = chmax(sl), chmin(sl)
    yl = luma(sl)
    neutral = (yl > 0.03) & (mx < 0.92) & ((mx - mn) / np.maximum(mx, 1e-6) < 0.14)
    gains = np.ones(3, np.float32)
    if neutral.mean() > 0.005:
        means = sl[neutral].mean(axis=0)
        g = means[1] / np.maximum(means, 1e-6)
        cast = float(np.max(np.abs(np.log(g))))
        if cast > 0.02:
            gains = np.exp(0.6 * np.log(g)).astype(np.float32)
            gains = np.clip(gains, 0.88, 1.15)
    if warmth:
        gains *= np.array([1 + 0.06 * warmth, 1.0, 1 - 0.06 * warmth], np.float32)
    gains /= float(gains @ common.LUMA)  # keep overall brightness
    rep["wb_gains"] = [round(float(x), 3) for x in gains]

    # 2. exposure: bring the brightest important tones near white
    sl_wb = sl * gains
    yl = luma(sl_wb)
    p995 = float(np.percentile(yl, 99.5))
    med_s = float(np.median(linear_to_srgb(yl)))
    gain = 0.92 / max(p995, 1e-4)
    gain = min(max(gain, 0.75), 2.2)
    if med_s > 0.45:
        gain = min(gain, 1.25)
    gain *= 2.0 ** ev
    rep["exposure_ev"] = round(math.log2(gain), 2)
    if abs(math.log2(gain)) > 1.0:
        warnings.append("big exposure change")

    lin = srgb_to_linear(img)
    lin *= (gains * gain)  # lin is a fresh array, safe to change in place
    # gentle highlight roll-off instead of a hard clip
    knee = 0.85
    over = lin > knee
    if over.any():
        v = lin[over]
        lin[over] = knee + (1 - knee) * np.tanh((v - knee) / (1 - knee))
        del v
    del over
    rgb = linear_to_srgb(lin, inplace=True)
    del lin
    y = luma(rgb)

    if style == "bw":
        mono = rgb @ np.array([0.30, 0.59, 0.11], np.float32)
        rgb = np.repeat(mono[..., None], 3, axis=2)
        y = mono

    # stats on the exposure-corrected small image
    ys = cv2.resize(y, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_AREA)
    med, std = float(np.median(ys)), float(ys.std())
    p005 = float(np.percentile(ys, 0.5))
    bright_frac = float((ys > 0.85).mean())

    # 3. black point (removes haze / flatness). Takes away most of a lifted black
    # level but not all of it, so misty scenes keep some of their mood.
    bp = min(0.75 * max(p005 - 0.01, 0.0), 0.18) if p005 > 0.025 else 0.0
    rep["black_point"] = round(bp, 3)

    # 4. shadows and highlights, applied through an edge-aware brightness map
    base = fast_guided_base(y)
    s_amt = st["shadows"] * float(np.clip((0.42 - med) / 0.25, 0.15, 1.0))
    h_amt = st["highlights"] * float(np.clip((bright_frac - 0.01) / 0.12, 0.0, 1.0))
    t_sh = clamp(1 - base / 0.5)
    t_hi = clamp((base - 0.65) / 0.35)
    local_gain = 1 + s_amt * t_sh * t_sh - h_amt * t_hi * t_hi
    del base, t_sh, t_hi
    rep["shadows"], rep["highlights"] = round(s_amt, 2), round(h_amt, 2)

    y1 = clamp((y * local_gain - bp) / (1 - bp))
    del local_gain

    # 5. contrast: an S-curve, stronger for flat photos
    k = st["contrast"] * (0.05 + 0.25 * float(np.clip((0.24 - std) / 0.12, 0, 1)))
    k = min(k, 0.45)
    y2 = (1 - k) * y1 + k * (y1 * y1 * (3 - 2 * y1))
    rep["contrast"] = round(k, 2)
    del y1

    # 6. clarity: local contrast in the midtones
    if st["clarity"] > 0:
        sigma = max(H, W) / 150.0
        detail = y2 - blur_large(y2, sigma)
        y2 = clamp(y2 + st["clarity"] * detail * (4 * y2 * (1 - y2)))
        del detail
    rep["clarity"] = st["clarity"]

    # apply brightness changes to colour, keeping hue
    ratio = y2 / np.maximum(y, 1e-4)
    clamp(ratio, 0, 4)
    rgb *= ratio[..., None]
    del ratio
    rgb = fit_gamut(rgb, y2)

    # 7. vibrance (boosts muted colours more than strong ones) and saturation
    if style != "bw" and (st["vibrance"] or st["saturation"]):
        yc = luma(rgb)
        sat = chmax(rgb) - chmin(rgb)
        factor = 1 + st["vibrance"] * (1 - clamp(sat / 0.6)) + st["saturation"]
        rgb = yc[..., None] + (rgb - yc[..., None]) * factor[..., None]
        rgb = fit_gamut(rgb, yc)
        del sat, factor

    # 8. noise reduction (only when the photo needs it)
    nz = noise_sigma(luma(rgb))
    rep["noise"] = round(nz, 2)
    noisy = nz > 2.2 or ((iso or 0) >= 6400 and nz > 1.2)
    if noisy:
        h_l = float(np.clip(1.2 * nz, 3, 10))
        ycc = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)
        yy = (np.clip(ycc[..., 0], 0, 1) * 255 + 0.5).astype(np.uint8)
        yy = cv2.fastNlMeansDenoising(yy, None, h_l, 7, 21).astype(np.float32) / 255.0
        # keep a little grain so it doesn't look plastic
        ycc[..., 0] = 0.8 * yy + 0.2 * ycc[..., 0]
        cs = 1.0 + nz / 2.0
        ycc[..., 1] = cv2.GaussianBlur(ycc[..., 1], (0, 0), cs)
        ycc[..., 2] = cv2.GaussianBlur(ycc[..., 2], (0, 0), cs)
        rgb = clamp(cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB))
        del ycc, yy
        rep["denoise"] = round(h_l, 1)
    else:
        rep["denoise"] = 0

    # 9. sharpening on edges only (keeps soft backgrounds smooth)
    rgb = sharpen(rgb, amount=st["sharpen"] * (0.6 if noisy else 1.0))
    rep["warnings"] = warnings
    return rgb


def sharpen(rgb, amount=0.9, radius=None):
    H, W = rgb.shape[:2]
    if radius is None:
        mp_ = H * W / 1e6
        radius = 0.6 if mp_ < 6 else 0.8 if mp_ < 16 else 1.0 if mp_ < 30 else 1.2
    y = luma(rgb)
    detail = y - cv2.GaussianBlur(y, (0, 0), radius)
    yb = cv2.GaussianBlur(y, (0, 0), 1.5)
    gx = cv2.Sobel(yb, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(yb, cv2.CV_32F, 0, 1, ksize=3)
    mask = smoothstep(0.02, 0.10, np.sqrt(gx * gx + gy * gy))
    # don't let sharpening cause bright/dark outlines
    d = clamp(amount * detail * mask, -0.12, 0.12)
    return clamp(rgb + d[..., None])


def _save_jpeg(arr, path, exif, icc, quality):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8))
    kw = {"quality": quality, "subsampling": 0, "optimize": True}
    if exif:
        kw["exif"] = exif
    if icc:
        kw["icc_profile"] = icc
    try:
        im.save(path, **kw)
    except Exception:
        kw.pop("exif", None)
        im.save(path, **kw)


def social_version(rgb, long_edge=2048):
    H, W = rgb.shape[:2]
    s = long_edge / max(H, W)
    if s >= 1:
        return rgb
    small = cv2.resize(rgb, (int(round(W * s)), int(round(H * s))), interpolation=cv2.INTER_AREA)
    return sharpen(small, amount=0.45, radius=0.6)


def compare_image(before, after, path, width=1600):
    def prep(a):
        h, w = a.shape[:2]
        s = (width / 2 - 6) / w
        return common.to_float(cv2.resize(a, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA))

    b, a = prep(before), prep(after)
    h = max(b.shape[0], a.shape[0])
    canvas = np.full((h + 34, b.shape[1] + a.shape[1] + 12, 3), 0.1, np.float32)
    canvas[34:34 + b.shape[0], 0:b.shape[1]] = b
    canvas[34:34 + a.shape[0], b.shape[1] + 12:] = a
    im = Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8))
    from PIL import ImageDraw

    d = ImageDraw.Draw(im)
    f = common.font(20, bold=True)
    d.text((8, 6), "Before", fill=(230, 230, 230), font=f)
    d.text((b.shape[1] + 20, 6), "After", fill=(230, 230, 230), font=f)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, quality=88)


def read_picks(path):
    with open(path, newline="") as f:
        lines = [l for l in f.read().splitlines() if l.strip() and not l.lstrip().startswith("#")]
    rows = list(csv.DictReader(lines))
    for r in rows:
        for c in PICK_COLUMNS:
            r[c] = (r.get(c) or "").strip()
    return [r for r in rows if r["id"]]


def _row_hash(row, default_style):
    keys = ["aspect", "cx", "cy", "zoom", "rotate", "ev", "warmth", "style"]
    s = json.dumps([row.get(k, "") for k in keys] + [default_style, VERSION])
    return hashlib.sha1(s.encode()).hexdigest()[:12]


VERSION = 2


def run(work, picks_path, out, only=None, force=False, compare=False, default_style="natural",
        social_edge=2048, quality=95, review_dir=None):
    cat = common.load_catalog(work)
    recs = common.by_id(cat)
    picks = read_picks(picks_path)
    if only:
        wanted = set(only)
        picks = [p for p in picks if p["id"] in wanted]
    out = os.path.abspath(os.path.expanduser(out))
    common.mark_folder(out, ".wildlife-kit-output", "Made by Wildlife Photo Kit (edited copies).")
    review_dir = review_dir or os.path.join(work, "review", "compare")
    log_path = os.path.join(out, "edit_log.csv")
    log = {}
    if os.path.exists(log_path):
        with open(log_path, newline="") as f:
            for r in csv.DictReader(f):
                log[r["id"]] = r
    cols = ["id", "date", "species", "caption", "source", "edited", "social", "status", "settings",
            "warnings", "hash"]
    total = len(picks)
    for i, p in enumerate(picks, 1):
        r = recs.get(p["id"])
        if not r:
            print(f"[{i}/{total}] {p['id']}: unknown id, skipped")
            continue
        style = p["style"] or default_style
        h = _row_hash(p, default_style)
        base = os.path.splitext(os.path.basename(r["rel"]))[0]
        name = f"{r['id']}_{base}.jpg"
        rel_full = os.path.join("Edited", r["date"][:4], r["date"], name)
        rel_social = os.path.join("Social", r["date"][:4], r["date"], name)
        old = log.get(p["id"])
        up_to_date = (not force and old and old.get("hash") == h and old.get("status") == "ok"
                      and os.path.exists(os.path.join(out, rel_full))
                      and (not compare or os.path.exists(os.path.join(review_dir, f"{r['id']}.jpg"))))
        if up_to_date:
            old.update(species=p["species"], caption=p["caption"])
            print(f"[{i}/{total}] {p['id']}: already done")
            continue
        try:
            img, exif, icc = common.open_full(r["path"], r["kind"])
            img = rotate_and_trim(img, _f(p["rotate"], 0.0))
            Hh, Ww = img.shape[:2]
            x0, y0, x1, y1 = crop_box(Ww, Hh, p["aspect"] or "orig", _f(p["cx"], 0.5), _f(p["cy"], 0.5),
                                      _f(p["zoom"], 1.0))
            img = img[y0:y1, x0:x1]
            rep = {}
            edited = develop(img, iso=r.get("iso"), style=style, ev=_f(p["ev"], 0.0),
                             warmth=_f(p["warmth"], 0.0), report=rep)
            warn = rep.pop("warnings", [])
            mp_ = edited.shape[0] * edited.shape[1] / 1e6
            if mp_ < 3:
                warn.append(f"small after crop ({mp_:.1f} MP)")
            if r.get("flags") and "soft" in r["flags"]:
                warn.append("may be soft")
            _save_jpeg(edited, os.path.join(out, rel_full), exif, icc, quality)
            _save_jpeg(social_version(edited, social_edge), os.path.join(out, rel_social), exif, icc, 92)
            if compare:
                compare_image(img, edited, os.path.join(review_dir, f"{r['id']}.jpg"))
            log[p["id"]] = {"id": p["id"], "date": r["date"], "species": p["species"], "caption": p["caption"],
                            "source": r["path"], "edited": rel_full, "social": rel_social, "status": "ok",
                            "settings": json.dumps(rep), "warnings": "; ".join(warn), "hash": h}
            print(f"[{i}/{total}] {p['id']}: done {'(' + '; '.join(warn) + ')' if warn else ''}", flush=True)
        except Exception as e:
            log[p["id"]] = {"id": p["id"], "date": r["date"], "source": r["path"], "status": "error",
                            "warnings": f"{type(e).__name__}: {e}"[:300], "hash": ""}
            print(f"[{i}/{total}] {p['id']}: FAILED {type(e).__name__}: {e}", flush=True)
        os.makedirs(out, exist_ok=True)
        with open(log_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for row in sorted(log.values(), key=lambda x: x["id"]):
                w.writerow(row)
    print(f"Edited photos are in {os.path.join(out, 'Edited')} (social-size copies in "
          f"{os.path.join(out, 'Social')})")
