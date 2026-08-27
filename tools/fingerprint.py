#!/usr/bin/env python3
"""Give every function in both builds of Operation Neptune the same kind of
fingerprint, so the 16-bit build's names can be carried across to the 32-bit one.

The two builds come from one source tree through one compiler, but they are not
laid out the same way -- the 16-bit link puts 24 KB of Borland runtime first and
the 32-bit link does not -- so position alone will not match them up. What does
survive is behaviour: a function that called GetTextExtentPoint and TextOut in
1997 still calls them in the other build.

    16-bit   ONWIN.MAP says where every named function starts; the NE relocation
             table says which imported API each fixup site refers to. No
             disassembly needed -- a relocation inside a function's byte range
             IS a call to that API.
    32-bit   the lifted call graph already has it: every call to one of the
             143 Borland import thunks resolves to an IAT slot, and the PE
             import directory names the slot.

    python tools/fingerprint.py -o work/fingerprints.json
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'tools')))
from tools.ne.ne_parse import parse_ne
from tools.pe.pe_analyze import analyze_pe, build_iat_map


# ---------------------------------------------------------------- 16-bit side

def import_label(ne, data, rel):
    """Name the API a relocation refers to. Import-by-name gives the string
    outright; import-by-ordinal gives MODULE.N, which still matches across the
    two builds as long as we compare like with like."""
    mod = ne.module_names[rel.module_idx - 1] if 0 < rel.module_idx <= len(ne.module_names) else '?'
    if (rel.flags & 3) == 2:                     # import by name
        off = ne.ne_offset + ne.import_table_off + rel.ordinal
        if 0 < off < len(data):
            n = data[off]
            return f"{mod}.{data[off + 1:off + 1 + n].decode('ascii', 'replace')}"
    return f"{mod}.#{rel.ordinal}"


def reloc_sites(seg, rel):
    """Every offset this relocation applies to.

    NE relocations are a chained list: the record names one offset, and the word
    already sitting there points at the next site wanting the same fixup, until
    0xFFFF. Reading only the head attributes one call to one function and loses
    the rest -- which for a heavily used API is most of them.
    """
    if rel.additive:
        return [rel.offset]
    sites, off, seen = [], rel.offset, set()
    while off != 0xFFFF and 0 <= off < len(seg.data) - 1 and off not in seen:
        seen.add(off)
        sites.append(off)
        off = struct.unpack_from('<H', seg.data, off)[0]
    return sites


def sixteen_bit(exe, symbols):
    ne = parse_ne(exe)
    data = open(exe, 'rb').read()

    # Every import fixup site, by segment.
    sites = {}                                   # seg -> [(off, label)]
    for seg in ne.segments:
        if not seg.is_code:
            continue
        acc = []
        for rel in seg.relocations:
            if (rel.flags & 3) in (1, 2):
                label = import_label(ne, data, rel)
                for off in reloc_sites(seg, rel):
                    acc.append((off, label))
        sites[seg.index] = sorted(acc)

    # The map's own module boundaries, and the functions inside them.
    segs = sorted([s for s in symbols['segments'] if s['class'] == 'CODE'],
                  key=lambda s: (s['seg'], s['off']))

    def module_of(seg, off):
        best = None
        for s in segs:
            if s['seg'] == seg and s['off'] <= off < s['off'] + s['len']:
                if best is None or s['len'] < best['len']:
                    best = s
        return best

    pubs = sorted(symbols['publics'], key=lambda p: (p['seg'], p['off']))
    out = []
    for i, p in enumerate(pubs):
        m = module_of(p['seg'], p['off'])
        if not m:
            continue
        # A function runs to the next public in the same segment, or to the end
        # of its module. Data symbols land in DATA-class segments and are
        # skipped by module_of above.
        end = m['off'] + m['len']
        for q in pubs[i + 1:]:
            if q['seg'] != p['seg']:
                break
            if q['off'] > p['off']:
                end = min(end, q['off'])
                break
        calls = sorted({lbl for off, lbl in sites.get(p['seg'], [])
                        if p['off'] <= off < end})
        out.append({'name': p['name'], 'module': m['module'].replace('_TEXT', ''),
                    'seg': p['seg'], 'off': p['off'], 'size': max(0, end - p['off']),
                    'calls': calls, 'edges': []})

    # Far-call edges, from the internal relocations.
    #
    # In a large-model 16-bit build every call that leaves a segment is a far
    # call and therefore relocated, so the inter-module call graph is sitting in
    # the relocation table. Near calls inside a segment are self-relative and
    # invisible here -- which is fine, because the edges that cross modules are
    # the ones that identify a function.
    starts = {}
    for i, f in enumerate(out):
        starts.setdefault(f['seg'], []).append((f['off'], i))
    for k in starts:
        starts[k].sort()

    def fn_at(seg, off):
        lst = starts.get(seg)
        if not lst:
            return None
        lo, hi = 0, len(lst) - 1
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if lst[mid][0] <= off:
                best = lst[mid][1]; lo = mid + 1
            else:
                hi = mid - 1
        return best

    code_segs = {s.index for s in ne.segments if s.is_code}
    for seg in ne.segments:
        if not seg.is_code:
            continue
        for rel in seg.relocations:
            if (rel.flags & 3) != 0 or rel.target_seg not in code_segs:
                continue
            tgt = fn_at(rel.target_seg, rel.target_off)
            if tgt is None:
                continue
            for off in reloc_sites(seg, rel):
                src = fn_at(seg.index, off)
                if src is not None and src != tgt:
                    out[src]['edges'].append(tgt)
    for f in out:
        f['edges'] = sorted(set(f['edges']))
    return out


# ---------------------------------------------------------------- 32-bit side

def thirty_two_bit(exe, functions):
    info = analyze_pe(exe)
    iat = build_iat_map(info)                    # slot VA -> (dll, name)
    data = open(exe, 'rb').read()

    def rva_to_off(rva):
        for s in info.sections:
            if s.virtual_address <= rva < s.virtual_address + max(s.virtual_size, s.raw_size):
                return s.raw_offset + (rva - s.virtual_address)
        return None

    # Borland calls every import through a six-byte `jmp dword ptr [slot]`
    # thunk, so a call to a thunk is a call to the API behind it.
    thunks = {}
    for f in functions:
        va = int(f['address'], 16)
        off = rva_to_off(va - info.image_base)
        if off is None or off + 6 > len(data):
            continue
        if data[off] == 0xFF and data[off + 1] == 0x25:
            slot = struct.unpack_from('<I', data, off + 2)[0]
            if slot in iat:
                dll, name = iat[slot]
                thunks[va] = f"{dll.split('.')[0].upper()}.{name}"

    out = []
    for f in functions:
        va = int(f['address'], 16)
        if va in thunks:
            continue                             # a thunk is not a function
        calls = sorted({thunks[int(t, 16)] for t in f['calls_to'] if int(t, 16) in thunks})
        out.append({'va': va, 'size': f['size'], 'calls': calls,
                    'targets': sorted({int(t, 16) for t in f['calls_to']
                                       if int(t, 16) not in thunks})})
    out.sort(key=lambda f: f['va'])
    index = {f['va']: i for i, f in enumerate(out)}
    for f in out:
        f['edges'] = sorted({index[t] for t in f['targets'] if t in index})
        del f['targets']
    return out, thunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ne', default='original/ONWINCD/ONWIN.EXE')
    ap.add_argument('--pe', default='original/ONWINCD/ONWIN32.EXE')
    ap.add_argument('--symbols', default='work/symbols.json')
    ap.add_argument('--functions', default='work/pipeline_functions.json')
    ap.add_argument('-o', '--output', default='work/fingerprints.json')
    a = ap.parse_args()

    symbols = json.load(open(a.symbols))
    ne16 = sixteen_bit(a.ne, symbols)
    pe32, thunks = thirty_two_bit(a.pe, json.load(open(a.functions)))

    n16 = sum(1 for f in ne16 if f['calls'])
    n32 = sum(1 for f in pe32 if f['calls'])
    e16 = sum(len(f['edges']) for f in ne16)
    e32 = sum(len(f['edges']) for f in pe32)
    print(f"16-bit: {len(ne16):5d} named functions, {n16} call an API, {e16} far-call edges")
    print(f"32-bit: {len(pe32):5d} functions ({len(thunks)} import thunks set aside), "
          f"{n32} call an API, {e32} call edges")

    api16 = {c for f in ne16 for c in f['calls']}
    api32 = {c for f in pe32 for c in f['calls']}
    common = api16 & api32
    print(f"APIs:   {len(api16)} in the 16-bit build, {len(api32)} in the 32-bit, "
          f"{len(common)} named the same in both")

    json.dump({'ne16': ne16, 'pe32': pe32}, open(a.output, 'w'), indent=1)
    print(f"wrote {a.output}")


if __name__ == '__main__':
    main()
