#!/usr/bin/env python3
"""Parse ONWIN.MAP -- the Borland linker map that shipped on the Operation
Neptune CD -- into JSON.

Two things come out of it that a stripped binary can't give us:

  segments  the module each chunk of code came from (ACTION, BALLAST, SONAR...),
            because the linker lists every .OBJ's contribution to every segment
  publics   1,273 named functions and variables at seg:off

The map is for the 16-bit ONWIN.EXE build, but ONWIN32.EXE is the same source
through the same Borland compiler, so the names are the naming oracle for both.

    python tools/parse_map.py original/ONWINCD/ONWIN.MAP -o work/symbols.json
"""
import json, re, sys, argparse

SEG_LINE = re.compile(r"^\s*([0-9A-F]{4}):([0-9A-F]{4})\s+([0-9A-F]+)H\s+(\S+)\s+(\S+)\s*$")
PUB_LINE = re.compile(r"^\s*([0-9A-F]{4}):([0-9A-F]{4})\s+(idle\s+)?(\S.*?)\s*$")


def parse(path):
    segments, publics = [], []
    section = "segments"
    for line in open(path, "r", errors="replace"):
        if "Publics by Name" in line:
            section = "publics"; continue
        if "Publics by Value" in line:
            section = "byvalue"; continue          # same data, sorted; skip
        if section == "segments":
            m = SEG_LINE.match(line)
            if m:
                seg, off, length, name, cls = m.groups()
                segments.append({"seg": int(seg, 16), "off": int(off, 16),
                                 "len": int(length, 16), "module": name, "class": cls})
        elif section == "publics":
            m = PUB_LINE.match(line)
            if m:
                seg, off, idle, name = m.groups()
                publics.append({"seg": int(seg, 16), "off": int(off, 16),
                                "name": name, "idle": bool(idle)})
    return {"segments": segments, "publics": publics}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("-o", "--output")
    a = ap.parse_args()
    out = parse(a.map)

    # ponytail: the C++ runtime (string::, typeinfo::, operator new) is Borland's,
    # not the game's -- flag it rather than filter it, callers can decide.
    game = [p for p in out["publics"] if p["name"].startswith("_")]
    mods = sorted({s["module"] for s in out["segments"] if s["class"] == "CODE"})
    print(f"segments : {len(out['segments'])} contributions, {len(mods)} distinct CODE modules")
    print(f"publics  : {len(out['publics'])} ({len(game)} C-linkage, rest Borland C++ runtime)")

    if a.output:
        json.dump(out, open(a.output, "w"), indent=1)
        print(f"wrote {a.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
