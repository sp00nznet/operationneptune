# Naming the lifted functions

`ONWIN.MAP` names 760 functions in the 16-bit build. `ONWIN32.EXE` is the same
source through the same compiler and has none, because a PE keeps no map. Every
one of the 1,205 lifted functions is `sub_0041xxxx`.

Carrying the names across is the highest-value thing left in this project: it
turns every trace, every crash dump and every `NEP_WATCH` line from hex into the
game's own vocabulary. This is what has been tried, what the data actually says,
and where the wall is.

## Position does not work

The obvious idea is that both builds link the same object files in the same
order, so the functions line up and the names can be poured across.

They do not line up. The 16-bit link puts 24 KB of Borland runtime (`_TEXT`)
first; the 32-bit link does not. The four dialog procedures sit at rank 214-217
of 760 in the map and at rank 42-45 of 1,205 in the PE — 28% of the way in
against 3.5%.

Scaling does not rescue it either. Those four procedures are the one place where
the truth is known on both sides: the 16-bit build lists them in its
resident-name table and the PE exports them, Borland-mangled, from `.edata`.
Measured against each other:

| | 16-bit gap | 32-bit gap | ratio |
|---|---:|---:|---:|
| `OKDialogProc` → `NoMIDIProc` | 98 | 70 | 0.71 |
| → `DesignedFor640X480Proc` | 229 | 191 | 0.83 |
| → `RunIn16ColorProc` | 371 | 317 | 0.85 |

The 16-to-32-bit size ratio varies from **0.71 to 0.85 inside one 997-byte
module**. Instruction encodings simply do not scale uniformly. With 1,066
functions in 176 KB — one every 165 bytes — a geometric fit loose enough to
accept the truth accepts everything: an early attempt placed 53 of 96 modules
with a "perfect" score, at mutually contradictory addresses.

That is not a tuning problem. It is the wrong model.

## What does carry across

Behaviour. `tools/fingerprint.py` builds the same two things for each build:

- **The call graph.** In a large-model 16-bit build every call that leaves a
  segment is far, and therefore relocated, so the inter-module call graph is
  sitting in the NE relocation table — no disassembly needed. 1,860 edges on the
  16-bit side, 3,475 on the 32-bit.
- **Which APIs each function calls.** Same trick: an import relocation inside a
  function's byte range *is* a call to that API. NE relocations are chained, so
  the chains have to be walked — reading only each record's head offset finds
  one call site and misses the rest.

The catch is that the 16-bit build imports **by ordinal** (`GDI.#45`) and the
32-bit build by name (`TextOutA`), so the fingerprints are not directly
comparable. But one thing does survive the port: **which library the call lands
in**. KERNEL becomes KERNEL32, USER becomes USER32, GDI becomes GDI32,
MMSYSTEM becomes WINMM.

## The bootstrap

`tools/name_functions.py` uses that to start, and then feeds on itself:

1. **Eight anchors.** Four exported by name from both builds. Four more from
   functions whose library profile — *n* KERNEL, *n* USER, *n* GDI, *n* MMSYSTEM
   — is unique on both sides at once.

2. **Each pair constrains the ordinal table.** If `_KillWave` calls
   `MMSYSTEM.405`, `.407` and `.411`, and its match calls `waveOutClose`,
   `waveOutReset` and `waveOutUnprepareHeader`, those three ordinals are those
   three functions in some order. Intersect across every pair, then eliminate:
   an ordinal pinned to one name takes that name off every other ordinal.

3. **A known ordinal identifies more functions**, which gives more pairs, which
   pins down more ordinals.

4. **The call graph fills the gaps** — a function whose callers and callees are
   all matched has only one candidate itself.

Nothing is hardcoded from an outside reference, so everything it concludes is
derived from these two binaries. The four profile-unique anchors it finds check
out against their own names, which is the useful thing about them:

| Name (from the map) | 16-bit ordinals | 32-bit APIs |
|---|---|---|
| `_KillWave` | `MMSYSTEM.405/407/411`, `USER.109` | waveOutClose, waveOutReset, waveOutUnprepareHeader, PeekMessage |
| `_writeDBchar` | `GDI.2/33/45`, `KERNEL.90` | SelectObject, SetBkMode, TextOut, lstrlen |
| `_ShutDownMIDIDriver` | `KERNEL.88/89`, `MMSYSTEM.701` | lstrcat, lstrcpy, mciSendCommand |
| `_replace_system_colors` | `GDI.373`, `USER.66/68/180/181` | SetSystemPaletteUse, GetDC, ReleaseDC, GetSysColor, SetSysColors |

A function called `KillWave` calling the three `waveOut` shutdown entry points
is not a coincidence, and `ShutDownMIDIDriver` reaching for `mciSendCommand`
independently confirms what the bring-up found the hard way — that this game
drives its MIDI through MCI.

Six Win16 ordinals fall out of those four pairs, and they are right:

```
GDI.#373      = SetSystemPaletteUse
KERNEL.#90    = lstrlen
MMSYSTEM.#701 = mciSendCommand
USER.#88      = EndDialog
USER.#98      = IsDlgButtonChecked
USER.#109     = PeekMessage
```

## Where the wall is

It stops there. Eight functions, six ordinals, no third round.

The deadlock is exactly the bootstrap's own shape: **ordinals come from matched
pairs, and pairs need known ordinals.** Six known ordinals are not enough to
make any further function uniquely identifiable — `PeekMessage` alone is called
by dozens — and the call graph cannot help because the eight anchors are mostly
leaves. The dialog procedures are called by USER, not by the game.

The matcher only accepts a pair when it is the best candidate for *both* halves.
That is deliberate: a wrong name does not stay wrong in one place, it propagates
into every round after it, and 1,205 functions confidently mislabelled is worse
than 1,205 honestly numbered.

## What would break it open

In rough order of effort:

1. **A Win16 ordinal table.** KERNEL, USER, GDI and MMSYSTEM ordinals are
   published and stable. About 120 entries covers everything this binary
   imports, and it turns all 88 API-calling 16-bit functions into directly
   comparable fingerprints in one step — which is enough seeds for the call
   graph to carry the rest. This is the obvious next move; it is only not done
   here because a table typed from memory would be a table with mistakes in it,
   and mistakes propagate.
2. **Call-site counts instead of call sets.** The fingerprints currently record
   *which* APIs a function calls, not how many times. A function calling
   `TextOut` three times is a different fingerprint from one calling it once.
   The 16-bit side already has this (relocation chains give every site); the
   32-bit side needs the per-call-site data from `work/functions.json` rather
   than the deduplicated `calls_to`.
3. **Data references.** The map names globals as well as functions —
   `_BallastParams`, `_SectorData`, `_FoeSemaphore`. Which globals a function
   touches is a far richer fingerprint than which APIs it calls, and far more of
   the 760 have one. It needs the 16-bit data segment laid against the 32-bit
   one, which has the same scaling problem as the code but with a much simpler
   shape.
4. **IDA or BinDiff.** This is a solved problem in that world, and the two
   binaries are exactly the input those tools are built for.

## Running it

```bash
python tools/fingerprint.py                    # both call graphs, both API sets
python tools/name_functions.py --dump-ordinals # the matcher, and what it derived

# whatever it produced, into the lift
python tools/run_pipeline.py original/ONWINCD/ONWIN32.EXE --all \
    --output src/recomp/gen --stubs src/recomp/imports_stub.c \
    --names work/names.json
```

Named functions come out as `MODULE_name` — `WWAVE_KillWave`, not `KillWave` —
because two modules can hold a function of the same name, and a symbol that
collides is worse than one that is merely ugly.
