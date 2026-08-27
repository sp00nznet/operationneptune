# Phase 0 — Reconnaissance

> What are we looking at, before we touch anything.

## The target

**Operation Neptune** — The Learning Company, 1991, part of the *Super Solvers*
series. The unmanned *Galaxy* space capsule breaks up and crashes into the sea
with the research team's data canisters aboard, leaking toxins as it goes; you
take the mini-sub *Neptune* down zone by zone to recover the pieces. Every
hatch, foe and salvage job in the way is a maths or reading problem —
middle-school arithmetic, fractions, decimals, ratios and word problems, dressed
as a submarine sim.

This teardown targets the **Windows CD re-release** (`ONWINCD`, TLC Properties
Inc., v1.23, 1998) — the last and most complete build: 256-colour art, CD audio
speech, and a Smacker intro.

Same TLC lineage as the *Super Solvers* / *Treasure* games whose asset formats
were cracked earlier — see [FORMATS](FORMATS.md).

## Two builds ship in the same folder

`ONWINCD\` contains the game compiled twice, from one source tree, by Borland:

| | `ONWIN.EXE` | `ONWIN32.EXE` |
|---|---|---|
| Format | NE (16-bit segmented, Windows 3.x) | PE32 (i386, Windows GUI) |
| Size | 323,072 B | 237,056 B |
| Code | 196,877 B in 26 CODE segments | 176,128 B, one flat `CODE` section |
| Imports | GDI, KERNEL, USER, MMSYSTEM, TOOLHELP, WIN87EM | GDI32, KERNEL32, USER32, WINMM (139 fns) |
| Linker | Borland 6.1 | Borland 2.25 |
| Exports | 5 resident names | 5, Borland-mangled (`@OKDialogProc$qpvuiuil`) |

Both export the same four dialog procedures (`OKDialogProc`, `RunIn16ColorProc`,
`NoMIDIProc`, `DesignedFor640X480Proc`), which is what pins them to one source
tree. `INSTALL\AUTORUN.INI` settles which one actually ships:

```
PRODUCT_NAME="Operation Neptune"
PRODUCT_KEY="Onwin32.exe"
```

**The recomp targets `ONWIN32.EXE`.** Flat 32-bit, no segmentation, no Win16
thunk layer, and pcrecomp's `lift32` path is the mature one (fury3, encarta,
gta). The 16-bit build is not dead weight, though — see below.

## The linker map is still on the disc

`ONWINCD\ONWIN.MAP` (344,564 B, 24 Mar 1997) is the **Borland linker map for the
16-bit build, shipped by mistake**. It is the single most valuable file on the
CD:

- **111 segment contributions from 96 distinct CODE modules** — the game's own
  source-file layout, module by module: `ACTION`, `BALLAST`, `BUBBLES`, `SONAR`,
  `DEPTHG`, `FOES`, `FREEZER`, `HEATSEN`, `CAPSULE`, `LOCATE`, `LOCK` (the
  combination-lock puzzle — `_DoCombinationLockProblem`), `MATHPROB`, `WORLD`
  (`_GetSector`, `_FirstSectorOfZone`), and a `W*`-prefixed Windows portability
  layer (`WGRAPHHI`, `WMIDI`, `WWAVE`, `WMOUSE`, `WFILE`, `WSTARTUP`…).
- **1,273 named publics**, 1,058 of them the game's own C-linkage symbols:
  `_DrawSub`, `_CheckBallastAnswer`, `_do_sonar_graphics`, `_draw_bubbles`,
  `_GetCrackSolutionSubst`, `_FoeSemaphore`, `_BallastParams`, `_DepthParams`…
  The remaining 215 are Borland's C++ runtime (`string::`, `typeinfo::`,
  `operator new`) and can be ignored.

The addresses are 16-bit `seg:off` and do not transfer to the PE directly, but
the *names, module boundaries and code sizes* do: same source, same compiler,
same order. That makes the map a naming oracle for the lifted 32-bit functions
rather than a pile of `fn_00410A7B`. `tools/parse_map.py` turns it into JSON.

The biggest modules, by bytes of 16-bit code:

| Module | Bytes | What it is |
|---|---:|---|
| `_TEXT` | 24,168 | Borland runtime + default segment |
| `MATHPROB_TEXT` | 14,620 | the maths problem engine |
| `_TEXTB` | 14,032 | (runtime overflow segment) |
| `OPENING_TEXT` | 10,394 | intro sequence |
| `SIGNIN_TEXT` | 8,677 | player sign-in / roster |
| `WGRAPHHI_TEXT` | 6,713 | hi-colour graphics layer |
| `LOCK_TEXT` | 6,626 | airlock puzzle |
| `PRACTICE_TEXT` | 5,312 | practice mode |
| `NUMBERS_TEXT` | 4,953 | number entry / formatting |
| `ACTION_TEXT` | 4,220 | the submarine action loop |

The four `EDIT*` modules (`EDIT`, `EDITDECO`, `EDITFOES`, `EDITMATH`) link at
**zero bytes** — the level editor was `#ifdef`-ed out of the shipping build, but
the linker still recorded it. `_editfoes_is_compiled` survives as a public.

## Disc inventory (154 files)

```
ONWINCD/            the game
  ONWIN32.EXE       PE32 shipping executable          237,056
  ONWIN.EXE         NE 16-bit build                   323,072
  ONWIN.MAP         Borland linker map                344,564
  NEP.DLL           NE, all the game's text         1,086,976
  NEP256.DLL        NE, 1,158 RUND sprites          2,583,040
  NEPBG1.DLL        NE, backgrounds               10,036,224
  NEPBG2.DLL        NE, backgrounds                9,687,595
  NE0/1/2SOUND.DLL  NE, digital audio             14,091,788
  SOUNDS/           21 .MID
  HALLFAME.DAT      high scores
INSTALL/            installed-image source
  COMMON.RSC        NE resource file               5,906,624
  LABRNTH1/2.RSC    labyrinth maps
  READER1/2.RSC     reading-comprehension puzzles
  SORTER.RSC        sorting puzzles
  OT3.RSC, AUTORUN.RSC
  AUTO256.BMP       602x400 8-bit BMP — the 256-colour palette lives here
  *.MPS             14 plain-text scripts (see below)
ASSETS/             WS107A/WS109/WS203/WSCOMMON .GRP — WAV wrappers
MOVIES/             MV107A.SMK — Smacker video
ALIAS/ AOL/ CP/ EREG/ LICENSE/   installer, registration, AOL ad-ware
```

Nothing is packed or copy-protected. No SafeDisc, no LZEXE, no self-extractor
around the game binary — `SETUP.EXE` is an ordinary InstallShield stub and the
game files sit on the disc in the clear.

## The .MPS scripts are not the game

`INSTALL\*.MPS` are 4,029 lines of readable script source with `procedure`,
`Scene`, `include`, `play`, `voice`, `yield` and `UseResourceGroupFile`
keywords, complete with the author's initials in the comments. Tempting — but
they drive the **CD's demo browser** (`AUTORUN.EXE` + `AUTORUN.RSC`), previewing
*other* TLC titles, not Operation Neptune. Their vocabulary gives them away:
sneezeberries, beetle bags, snagnets, and characters called Joni and Santiago.

Worth keeping for the record; not on the recomp path.

## What this means for the plan

1. Lift `ONWIN32.EXE` with `lift32` -- flat, unpacked, four import DLLs. **Done:
   1,205 functions, 189K lines, no errors.**
2. Answer its 139 Win32 imports. **Done** -- most of them pass straight through
   to the real API, because this is a Win32 program running on Win32. The
   exceptions are in [the README](../README.md#what-it-draws-through).
3. Name the lifted functions from `ONWIN.MAP` rather than leaving them numbered.
   Not started; the highest-value thing left.
4. Assets are already understood -- the RUND sprite codec, the RLE tilemaps and
   the palette were cracked in earlier work on this same engine family. See
   [FORMATS](FORMATS.md).

## What the first run taught us

Things that were not visible from the binary alone, in the order they surfaced:

- **All drawing goes through WinG.** There is no `BitBlt` in the import table
  because `WING32.DLL` is loaded at runtime. The game asks it for a 640x800
  buffer to drive a 640x400 screen -- two pages, flipped by blitting from a
  different source `y`.
- **The 32-bit build reads its own resource DLLs by hand.** `NEP256.DLL` and
  friends are 16-bit NE modules that no 32-bit process could ever have
  `LoadLibrary`-ed, which is why this build imports the `_lopen`/`_lread`
  family. It opens all six with `CreateFileA` and parses them itself.
- **`NE2SOUND.DLL` is a checksum.** It is twelve bytes long, and `ONWINCD.INI`
  carries `NE2sound=12`. The game finds the file, compares the size against the
  INI, and refuses to start if they disagree -- a 1997 anti-piracy check that
  amounts to "is the CD really mounted".
- **The game quits over two environment checks** that no modern machine can
  pass: a Windows 3.1 MIDI mapper config file, and a 640x480 256-colour desktop.
  Both are its own INI switches.
- **Music and CD audio go through MCI, not the MIDI API.** `midiOutGetDevCapsA`
  is the only MIDI import there is; the score in `SOUNDS\*.MID` is opened as an
  MCI element and played.
- **The game draws into the WinG buffer two ways at once** -- sprites through
  the raw pointer, every string through real GDI into the WinG DC. Handing back
  a plain buffer renders the whole game except its text.
- **The narration loop never pumps messages.** It writes a buffer with
  `waveOutWrite` and then spins on `WHDR_DONE` in its own WAVEHDR, so anything
  that updates that flag on the message pump never runs and the intro stops dead
  on the first letter of "RED ALERT". The driver has to tell us directly.
- **It reads just outside the framebuffer.** The save-under behind a popup
  flush against the top-left corner starts two bytes and one row before the
  buffer. Harmless in 1996 when the DIB had neighbours; an access violation
  against a mapping of exactly the right size.
