#!/usr/bin/env python3
"""Carry the 16-bit build's function names across to the 32-bit one.

ONWIN.MAP names 760 functions in ONWIN.EXE. ONWIN32.EXE is the same source
through the same compiler and has none, because a PE keeps no map.

Position will not do it. The two builds are not laid out alike -- the 16-bit
link puts 24 KB of Borland runtime first, the 32-bit link does not -- and
scaling does not rescue it either: on WDLGS, the one module whose true position
is known from the PE's own export table, the 16-to-32-bit size ratio varies from
0.71 to 0.85 *within that single module*. A geometric fit loose enough to accept
the truth is loose enough to accept anything, at 1,066 functions in 176 KB.

What does carry across is behaviour, and it bootstraps:

  1. Eight anchors to start. Four are exported by name from both builds (the
     dialog procedures). Four more fall out of the library a call lands in,
     which survives the port even when the ordinal does not -- KERNEL becomes
     KERNEL32, MMSYSTEM becomes WINMM -- so a function that is the only one in
     its build calling three MMSYSTEM and one USER has exactly one candidate.

  2. Each matched pair constrains the Win16 ordinal table. If _KillWave calls
     MMSYSTEM.405, .407 and .411, and its match calls waveOutClose, waveOutReset
     and waveOutUnprepareHeader, those three ordinals are those three functions
     in some order. Intersect across every pair and the mapping collapses.

  3. A known ordinal makes more functions identifiable, which gives more pairs,
     which pins down more ordinals. Round and round until it stops.

  4. What the API evidence cannot reach, the call graph can: a function whose
     callers and callees are matched has only one candidate itself.

No Win16 ordinal list is hardcoded, so everything concluded here is derived from
these two binaries; --dump-ordinals prints what it worked out.

    python tools/fingerprint.py
    python tools/name_functions.py -o work/names.json --dump-ordinals
"""
import argparse
import collections
import json
import math

# Both builds export these four by name; the PE addresses come from its export
# directory. This is the only fact written down rather than derived.
ANCHORS = {
    'OKDIALOGPROC':           0x004109BC,
    'NOMIDIPROC':             0x00410A02,
    'DESIGNEDFOR640X480PROC': 0x00410A7B,
    'RUNIN16COLORPROC':       0x00410AF9,
}

# The one correspondence the port cannot change: which library a call lands in.
DLL16 = {'KERNEL': 'K', 'USER': 'U', 'GDI': 'G', 'MMSYSTEM': 'M'}
DLL32 = {'KERNEL32': 'K', 'USER32': 'U', 'GDI32': 'G', 'WINMM': 'M'}


def dll_of(label, table):
    return table.get(label.split('.')[0])


def profile(calls, table):
    c = collections.Counter()
    for x in calls:
        d = dll_of(x, table)
        if d:
            c[d] += 1
    return tuple(sorted(c.items()))


def size_prior(a, b):
    """32-bit code is not the same size as 16-bit code, but an order of
    magnitude apart means these are not the same function."""
    if a <= 0 or b <= 0:
        return 0.5
    return max(0.0, 1.0 - abs(math.log(a / b)) / 1.6)


def invert(fns):
    pred = [[] for _ in fns]
    for i, f in enumerate(fns):
        for j in f['edges']:
            if 0 <= j < len(pred):
                pred[j].append(i)
    return pred


def seed(ne16, pe32):
    """The eight starting pairs: four by name, four by a library profile that is
    unique on both sides at once."""
    by_va = {f['va']: i for i, f in enumerate(pe32)}
    by_name = {f['name']: i for i, f in enumerate(ne16)}
    pairs = {}
    for name, va in ANCHORS.items():
        if name in by_name and va in by_va:
            pairs[by_name[name]] = by_va[va]

    p16, p32 = collections.defaultdict(list), collections.defaultdict(list)
    for i, f in enumerate(ne16):
        if f['calls']:
            p16[profile(f['calls'], DLL16)].append(i)
    for j, f in enumerate(pe32):
        if f['calls']:
            p32[profile(f['calls'], DLL32)].append(j)
    for k, v in p16.items():
        if len(v) == 1 and len(p32.get(k, [])) == 1:
            pairs.setdefault(v[0], p32[k][0])
    return pairs


def refine_ordinals(ne16, pe32, pairs, cand):
    """Every matched pair says: the ordinals this function calls in one build are
    the API names its match calls in the other, library by library."""
    for u, v in pairs.items():
        for d in 'KUGM':
            o = [c for c in ne16[u]['calls'] if dll_of(c, DLL16) == d]
            n = {c.split('.', 1)[1] for c in pe32[v]['calls'] if dll_of(c, DLL32) == d}
            if not o or not n:
                continue
            for x in o:
                cand[x] = (cand[x] & n) if x in cand else set(n)

    # An ordinal pinned to one name takes that name off every other ordinal.
    changed = True
    while changed:
        changed = False
        taken = {next(iter(s)): o for o, s in cand.items() if len(s) == 1}
        for o, s in cand.items():
            if len(s) == 1:
                continue
            drop = {n for n in s if n in taken}
            if drop and len(s - drop) >= 1:
                cand[o] = s - drop
                changed = True
    return {o: next(iter(s)) for o, s in cand.items() if len(s) == 1}


def run(ne16, pe32, min_score, verbose):
    succ16, succ32 = [f['edges'] for f in ne16], [f['edges'] for f in pe32]
    pred16, pred32 = invert(ne16), invert(pe32)

    pairs = seed(ne16, pe32)
    used32 = set(pairs.values())
    cand = {}
    print(f"seeded with {len(pairs)} pairs")

    known = {}
    rounds = 0
    while True:
        rounds += 1
        known = refine_ordinals(ne16, pe32, pairs, cand)

        # Only score pairs with something to go on: a shared known API, or a
        # neighbour already matched. Everything else is 800,000 pairs of noise.
        api16 = {}
        for i, f in enumerate(ne16):
            s = {known[c] for c in f['calls'] if c in known}
            if s and i not in pairs:
                api16[i] = s
        by_api = collections.defaultdict(set)
        for j, f in enumerate(pe32):
            if j in used32:
                continue
            for c in f['calls']:
                by_api[c.split('.', 1)[1]].add(j)

        scores = collections.defaultdict(float)
        for i, s in api16.items():
            for n in s:
                for j in by_api[n]:
                    scores[(i, j)] += 2.0
        for u, v in pairs.items():
            for a in succ16[u]:
                if a in pairs:
                    continue
                for b in succ32[v]:
                    if b not in used32:
                        scores[(a, b)] += 1.0
            for a in pred16[u]:
                if a in pairs:
                    continue
                for b in pred32[v]:
                    if b not in used32:
                        scores[(a, b)] += 1.0
        if not scores:
            break

        # A pair is taken only when it is the best for both halves. A wrong name
        # does not stay wrong in one place -- it propagates.
        best16, best32 = {}, {}
        for (a, b), s in scores.items():
            pa, pb = profile(ne16[a]['calls'], DLL16), profile(pe32[b]['calls'], DLL32)
            if pa and pb and pa != pb:
                continue                        # both call APIs, and disagree
            s *= 0.5 + 0.5 * size_prior(ne16[a]['size'], pe32[b]['size'])
            if s > best16.get(a, (0, None))[0]:
                best16[a] = (s, b)
            if s > best32.get(b, (0, None))[0]:
                best32[b] = (s, a)

        taken = 0
        for a, (s, b) in sorted(best16.items(), key=lambda kv: -kv[1][0]):
            if a in pairs or b in used32 or s < min_score:
                continue
            if best32.get(b, (0, None))[1] != a:
                continue
            pairs[a] = b
            used32.add(b)
            taken += 1
        if verbose:
            print(f"  round {rounds}: {len(known):3d} ordinals known, +{taken} pairs "
                  f"(total {len(pairs)})")
        if not taken:
            break

    return pairs, known


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fingerprints', default='work/fingerprints.json')
    ap.add_argument('--min-score', type=float, default=2.0)
    ap.add_argument('--dump-ordinals', action='store_true',
                    help='print the Win16 ordinal table it worked out')
    ap.add_argument('-o', '--output', default='work/names.json')
    ap.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args()

    d = json.load(open(a.fingerprints))
    ne16, pe32 = d['ne16'], d['pe32']
    pairs, known = run(ne16, pe32, a.min_score, a.verbose)

    if a.dump_ordinals:
        print(f"\n{len(known)} Win16 ordinals identified from the two builds:")
        for o in sorted(known, key=lambda x: (x.split('.')[0], int(x.split('#')[1]))):
            print(f"  {o:16s} = {known[o]}")

    names = {}
    per_mod = collections.Counter()
    for u, v in pairs.items():
        n = ne16[u]['name']
        if n.startswith('_'):
            n = n[1:]
        names[f"0x{pe32[v]['va']:08X}"] = {'name': n, 'module': ne16[u]['module']}
        per_mod[ne16[u]['module']] += 1

    print(f"\nnamed {len(names)} of {len(pe32)} functions across {len(per_mod)} modules")
    for m, c in per_mod.most_common(12):
        print(f"  {m:12s} {c}")
    json.dump(names, open(a.output, 'w'), indent=1, sort_keys=True)
    print(f"wrote {a.output}")


if __name__ == '__main__':
    main()
