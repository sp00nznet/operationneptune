# Operation Neptune Static Recompilation

Static recompilation of **Operation Neptune** (The Learning Company, 1991;
Windows CD re-release 1998) from its shipping Win32 binary to native C.
`ONWIN32.EXE` is an unpacked Borland-compiled PE that holds the whole game —
the submarine, the maths engine, the labyrinth, the puzzles — and this project
lifts every function in it to C and answers the Win32 API it expects with a
small runtime.

No emulator. The 1998 machine code, translated once and compiled for a machine
that did not exist when it shipped.

The CD also shipped `ONWIN.MAP`, the Borland **linker map** for the 16-bit build
of the same source tree. That is 96 named source modules and 1,058 named game
functions, left on the disc by accident, and it means the lifted code gets to be
called `_DrawSub` and `_CheckBallastAnswer` instead of `sub_00412A40`.

Built on the [pcrecomp](https://github.com/sp00nznet/pcrecomp) toolchain,
alongside the same-era DOS/Win16 arc of civ (1991), DinoPark Tycoon (1993),
Bolo Adventures III (1993) and El-Fish (1993).

## Status

**Phase 1 — lifted.** Recon is done and the whole binary is through the lifter.
Nothing runs yet.

LIFT_PLACEHOLDER

Assets are already solved. `tools/extract_assets.py`, carried over from the
earlier OpenGizmos clean-room work on this engine family, pulls the game apart
completely:

| | |
|---|---:|
| Sprites (RUND codec, `NEP256.DLL`) | 1,158 |
| WAV (speech and effects) | 488 |
| MIDI | 20 |
| Puzzle / definition resources | 852 |
| Smacker video | 1 |

## Where this came from

This is the second pass at Operation Neptune. The first was
**[OpenGizmos](https://github.com/sp00nznet/OpenGizmos)** — a clean-room
reimplementation of the whole TLC *Super Solvers* / *Treasure* family in C++
with SDL2, which got as far as a multi-game launcher, a working asset viewer and
a Neptune game module.

Clean-room got the *formats*. It could never get the *game*: the maths problem
generator, the foe behaviour, the exact balance of the ballast puzzle, the
sequencing of the opening — all of that is 176 KB of Borland output that nobody
was going to reimplement by observation.

So the formats work carries over intact and the behaviour comes from the
binary instead. Everything in [FORMATS](docs/FORMATS.md) is OpenGizmos'
findings; everything in [RECON](docs/RECON.md) and [SYMBOLS](docs/SYMBOLS.md)
is new.

## What's on the disc

Two builds of the same source ship side by side — `ONWIN.EXE` (NE, 16-bit) and
`ONWIN32.EXE` (PE32). `INSTALL\AUTORUN.INI` names `Onwin32.exe` as the product,
so that is the recomp target: flat 32-bit, four import DLLs, 139 functions, and
no DirectX anywhere. It is a `BitBlt`-and-`waveOut` game.

Nothing is packed or copy-protected.

See [RECON](docs/RECON.md) for the full teardown.

## Layout

```
original/       your copy of the retail CD (gitignored - see Legal)
docs/           RECON, SYMBOLS, FORMATS
tools/
  run_pipeline.py    PE analysis -> discovery -> lift -> C
  parse_map.py       ONWIN.MAP -> work/symbols.json
  extract_assets.py  TLC resource extractor (from OpenGizmos)
src/recomp/gen/ generated C (regenerated, not committed)
extracted/      extracted assets (regenerated, not committed)
work/           scratch analysis output
```

## Reproducing

You need your own copy of the Operation Neptune Windows CD. Copy its contents
into `original/`, then:

```bash
# The recompiler: PE -> functions -> C
python tools/run_pipeline.py original/ONWINCD/ONWIN32.EXE --all \
    --output src/recomp/gen --stubs src/recomp/imports_stub.c

# The symbol table the linker left behind
python tools/parse_map.py original/ONWINCD/ONWIN.MAP -o work/symbols.json

# Every sprite, sound and puzzle resource
python tools/extract_assets.py on original extracted/on --all
```

## Next

1. **Name the functions.** The map's addresses are 16-bit `seg:off` and do not
   transfer to the PE. Matching the two builds — by module size, call-graph
   shape and string references — turns 1,058 names into 1,058 named lifted
   functions. This is the highest-value thing left.
2. **Bridge the imports.** 139 stubs across GDI32, USER32, KERNEL32 and WINMM.
   pcrecomp's `runtime/compat` already maps most of this onto SDL2.
3. **Boot it.** Entry point, CRT startup, first frame.

## Legal

No game files are included. Operation Neptune is © 1991-1998 The Learning
Company / TLC Properties Inc., and copyright most likely still subsists through
the SoftKey → Mattel → Riverdeep → HMH chain. Bring your own disc.

The code in this repository is MIT licensed. See [LICENSE](LICENSE).
