"""Build a 'By Date' folder tree (Year / Year-Month-Day) without touching the originals.

On a Mac (APFS) the files are cloned, which takes no extra disk space. Where that
isn't possible it falls back to hard links, then to plain copies (after checking
there's room)."""

import os
import platform
import shutil
import subprocess

from . import common


def _clone(src, dst):
    if platform.system() != "Darwin":
        return False
    r = subprocess.run(["cp", "-c", "-p", src, dst], capture_output=True)
    return r.returncode == 0


def _hardlink(src, dst):
    try:
        os.link(src, dst)
        return True
    except OSError:
        return False


def _copy(src, dst):
    shutil.copy2(src, dst)
    return True


METHODS = {"clone": _clone, "hardlink": _hardlink, "copy": _copy}


def run(work, dest, mode="auto", include_copies=False):
    cat = common.load_catalog(work)
    dest = os.path.abspath(os.path.expanduser(dest))
    src_root = cat["src"]
    if dest == src_root or dest.startswith(src_root + os.sep):
        print("Note: the By Date folder is inside the photo folder; future scans will skip it.")
    common.mark_folder(dest, ".wildlife-kit-bydate",
                       "Made by Wildlife Photo Kit. Deleting this folder does not affect the original photos.")
    photos = [r for r in cat["photos"] if r.get("status") == "ok" and (include_copies or not r.get("dup_of"))]

    plan = []
    used = set()
    for r in photos:
        if r["date_source"] == "file-modified":
            folder = os.path.join(dest, "No camera date (sorted by file date)", r["date"][:4], r["date"])
        else:
            folder = os.path.join(dest, r["date"][:4], r["date"])
        base = os.path.basename(r["rel"])
        name, ext = os.path.splitext(base)
        target = os.path.join(folder, base)
        n = 2
        while target.lower() in used:
            target = os.path.join(folder, f"{name} ({n}){ext}")
            n += 1
        used.add(target.lower())
        plan.append((r["path"], target, r["bytes"]))

    order = ["clone", "hardlink", "copy"] if mode == "auto" else [mode]
    method = None
    todo = [(s, d, b) for s, d, b in plan if not (os.path.exists(d) and os.path.getsize(d) == b)]
    if not todo:
        print(f"Nothing to do: all {len(plan)} photos are already in {dest}")
        return
    # Find the first method that works on this drive.
    s, d, b = todo[0]
    os.makedirs(os.path.dirname(d), exist_ok=True)
    for m in order:
        if m == "copy":
            need = sum(b for _, _, b in todo)
            free = shutil.disk_usage(dest).free
            if need > free * 0.9:
                raise SystemExit(
                    f"Copying would need {need / 1e9:.1f} GB but only {free / 1e9:.1f} GB is free at {dest}.\n"
                    "Put the By Date folder on the same drive as the photos (so files can be cloned or "
                    "linked instead of copied), or free up space."
                )
        if METHODS[m](s, d):
            method = m
            break
    if method is None:
        raise SystemExit(f"Could not create {d} using: {', '.join(order)}")
    print(f"Using {method} ({'no extra disk space' if method != 'copy' else 'full copies'}) "
          f"for {len(todo)} photos into {dest}", flush=True)
    fn = METHODS[method]
    for i, (s, d, b) in enumerate(todo[1:], 2):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        if not fn(s, d):
            _copy(s, d)
        if i % 500 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
    years = sorted({os.path.relpath(d, dest).split(os.sep)[0] for _, d, _ in plan})
    print(f"Done. {len(plan)} photos in {dest} (folders: {', '.join(years)})")
    if method == "hardlink":
        print("Note: these are hard links. They share storage with the originals, so open them to view "
              "or copy, but don't edit them in place.")
