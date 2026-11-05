#!/usr/bin/env python3
"""Wildlife Photo Kit: sort photos by date, review them, and edit the best ones.

Run `python3 kit.py <step> --help` for options. The usual order is:
  scan -> organize -> sheets -> preview -> edit -> qa -> report
Your original photos are only ever read, never changed or moved.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DEFAULT_WORK = os.path.join(HERE, "work")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kit.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="read every photo: date, camera data, sharpness, thumbnails")
    p.add_argument("--src", required=True, help="folder with your photos (read only)")
    p.add_argument("--work", default=DEFAULT_WORK, help="working folder for thumbnails and lists")
    p.add_argument("--out", help="output folder (skipped during the scan if it's inside --src)")
    p.add_argument("--workers", type=int, help="parallel workers (default: CPU cores - 1)")
    p.add_argument("--burst-gap", type=float, default=4.0, help="seconds between frames of one burst")
    p.add_argument("--similar-gap", type=float, default=60.0, help="seconds for grouping near-identical shots")
    p.add_argument("--blur-threshold", type=float, default=80.0, help="sharpness below this is flagged 'soft'")
    p.add_argument("--fresh", action="store_true", help="rescan every photo instead of reusing earlier results")

    p = sub.add_parser("organize", help="build Year/Date folders (clones or links, originals untouched)")
    p.add_argument("--work", default=DEFAULT_WORK)
    p.add_argument("--dest", required=True, help="where to build the By Date folders")
    p.add_argument("--mode", choices=["auto", "clone", "hardlink", "copy"], default="auto")
    p.add_argument("--include-copies", action="store_true", help="also include exact duplicate files")

    p = sub.add_parser("sheets", help="contact sheets for the first review pass")
    p.add_argument("--work", default=DEFAULT_WORK)
    p.add_argument("--all", action="store_true", help="include every frame, not just the best of each burst")
    p.add_argument("--from", dest="date_from", help="first date, YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", help="last date, YYYY-MM-DD")
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--rows", type=int, default=5)

    p = sub.add_parser("preview", help="close-up sheets with a 100%% focus check, for chosen ids")
    p.add_argument("--work", default=DEFAULT_WORK)
    p.add_argument("ids", help="file with ids (one per line, or a CSV with an 'id' column) or comma-separated ids")
    p.add_argument("--name", default="preview", help="file name prefix for the sheets")

    p = sub.add_parser("zoom", help="100%% crops at chosen points of one photo, to check focus")
    p.add_argument("--work", default=DEFAULT_WORK)
    p.add_argument("id")
    p.add_argument("--at", action="append", required=True, metavar="X,Y",
                   help="point as fractions of width,height, e.g. 0.62,0.35 (repeat for more)")
    p.add_argument("--size", type=int, default=500)

    p = sub.add_parser("group", help="show every frame of one burst (give a photo id or group id)")
    p.add_argument("--work", default=DEFAULT_WORK)
    p.add_argument("id")

    p = sub.add_parser("edit", help="edit the photos listed in picks.csv")
    p.add_argument("--work", default=DEFAULT_WORK)
    p.add_argument("--picks", default=None, help="picks file (default: <work>/picks.csv)")
    p.add_argument("--out", required=True, help="where edited photos go")
    p.add_argument("--only", help="comma-separated ids to (re)do")
    p.add_argument("--force", action="store_true", help="redo even if already edited")
    p.add_argument("--compare", action="store_true", help="also save before/after images for review")
    p.add_argument("--style", default="natural", choices=["natural", "vivid", "soft", "bw"])
    p.add_argument("--social-size", type=int, default=2048, help="long edge of the social-media copies")

    p = sub.add_parser("qa", help="check sheets of edited photos")
    p.add_argument("--work", default=DEFAULT_WORK)
    p.add_argument("--out", required=True)

    p = sub.add_parser("report", help="build index.html gallery of the edited photos")
    p.add_argument("--work", default=DEFAULT_WORK)
    p.add_argument("--out", required=True)
    p.add_argument("--title", default="Wildlife picks")

    sub.add_parser("selftest", help="check the kit works, using made-up test photos")

    a = ap.parse_args(argv)
    if a.cmd == "scan":
        from photokit import scan
        scan.run(a.src, a.work, out=a.out, workers=a.workers, burst_gap=a.burst_gap,
                 similar_gap=a.similar_gap, blur_threshold=a.blur_threshold, fresh=a.fresh)
    elif a.cmd == "organize":
        from photokit import organize
        organize.run(a.work, a.dest, mode=a.mode, include_copies=a.include_copies)
    elif a.cmd == "sheets":
        from photokit import sheets
        sheets.contact_sheets(a.work, include_all=a.all, cols=a.cols, rows=a.rows,
                              date_from=a.date_from, date_to=a.date_to)
    elif a.cmd == "preview":
        from photokit import common, sheets
        sheets.previews(a.work, common.read_id_list(a.ids), name=a.name)
    elif a.cmd == "zoom":
        from photokit import sheets
        pts = [tuple(float(v) for v in p.split(",")) for p in a.at]
        sheets.zoom(a.work, a.id, pts, size=a.size)
    elif a.cmd == "group":
        from photokit import sheets
        sheets.group_sheet(a.work, a.id)
    elif a.cmd == "edit":
        from photokit import common, edit
        picks = a.picks or os.path.join(a.work, "picks.csv")
        edit.run(a.work, picks, a.out, only=common.read_id_list(a.only) if a.only else None,
                 force=a.force, compare=a.compare, default_style=a.style, social_edge=a.social_size)
    elif a.cmd == "qa":
        from photokit import sheets
        sheets.qa_sheets(a.work, a.out)
    elif a.cmd == "report":
        from photokit import report
        report.run(a.work, a.out, title=a.title)
    elif a.cmd == "selftest":
        from photokit import selftest
        selftest.run()


if __name__ == "__main__":
    main()
