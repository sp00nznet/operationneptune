/*
 * IAT bridge -- Win32 pass-through, plus the pieces that cannot pass through.
 *
 * Operation Neptune is a Win32 program running on Win32, so most of its 139
 * imports are answered by calling the same API for real. Three groups are not:
 *
 *   1. Anything returning a pointer. GlobalAlloc, GlobalLock and VirtualAlloc
 *      hand the game an address it stores in a 32-bit slot; on a 64-bit host
 *      the real return does not survive the truncation. These are served from
 *      the runtime's low heap instead.
 *   2. Anything taking a callback or a struct with pointers in it. A window
 *      procedure in the game is a VA with no machine code behind it, and
 *      WNDCLASSA / MSG / PAINTSTRUCT are laid out differently for 32- and
 *      64-bit. Those are translated field by field.
 *   3. WING32.DLL. The game loads it at runtime and does ALL of its drawing
 *      through it -- there is not one BitBlt in the import table. Windows has
 *      not shipped WinG since the 90s, so we are WinG now. See the shim below.
 *
 * The machinery (binding by name out of the image's own import directory, the
 * esp accounting, the unbridged report) comes from the gta recomp, where the
 * lesson was learned that hand-written IAT slot addresses drift out of step.
 */

/* windows.h first: winnt.h contains inline asm ("mov eax, ...") that the
 * RECOMP_GENERATED_CODE register aliases below would rewrite. */
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <mmsystem.h>
#pragma comment(lib, "winmm.lib")
#endif

#define RECOMP_GENERATED_CODE
#include "recomp_runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BRIDGE_BASE 0xB0000000u
#define MAX_BRIDGES 512

typedef struct {
    u32   iat_va;
    const char *name;
    void (*handler)(void);
    void *real;      /* resolved host API, for the generic pass-through */
    int   argc;      /* dwords the game pushed; the callee pops them */
} bridge_entry_t;

static bridge_entry_t bridges[MAX_BRIDGES];
static int num_bridges = 0;

/* Which bridge the dispatcher just resolved -- the generic pass-through and the
 * WinG shim both read it to tell themselves apart. */
static u32 g_bridge_hit;

static int g_verbose = 1;

/* ===================================================================
 * Binding: find each import by NAME in the image we mapped
 * =================================================================== */

static int same_import(const char *imported, const char *want) {
    if (*imported == '_' && *want != '_') imported++;
    while (*want && *imported && *imported != '@') {
        if (*want++ != *imported++) return 0;
    }
    return *want == 0 && (*imported == 0 || *imported == '@');
}

static u32 find_iat_slot(const char *want) {
    u32 nt = NEP_IMAGE_BASE + MEM32(NEP_IMAGE_BASE + 0x3C);
    u32 imports = MEM32(nt + 0x80);            /* DataDirectory[1].VirtualAddress */
    u32 desc;

    if (!imports) return 0;
    for (desc = NEP_IMAGE_BASE + imports; MEM32(desc + 12); desc += 20) {
        u32 int_rva = MEM32(desc + 0);         /* OriginalFirstThunk */
        u32 iat_rva = MEM32(desc + 16);        /* FirstThunk         */
        u32 i;
        if (!int_rva) int_rva = iat_rva;       /* some linkers omit the INT */
        for (i = 0; ; i++) {
            u32 thunk = MEM32(NEP_IMAGE_BASE + int_rva + i * 4);
            if (!thunk) break;
            if (!(thunk & 0x80000000u)) {
                const char *name = (const char *)(uintptr_t)
                                   ADDR(NEP_IMAGE_BASE + thunk + 2);
                if (same_import(name, want))
                    return NEP_IMAGE_BASE + iat_rva + i * 4;
            }
        }
    }
    return 0;
}

/* A callable address with no IAT slot behind it -- for the function pointers we
 * hand the game ourselves (GetProcAddress results for WinG). */
static u32 alloc_bridge(const char *name, void (*handler)(void), int argc) {
    if (num_bridges >= MAX_BRIDGES) {
        fprintf(stderr, "  BRIDGE: table full, '%s' unbridged\n", name);
        return 0;
    }
    bridges[num_bridges].iat_va  = 0;
    bridges[num_bridges].name    = name;
    bridges[num_bridges].handler = handler;
    bridges[num_bridges].real    = NULL;
    bridges[num_bridges].argc    = argc;
    return BRIDGE_BASE + num_bridges++;
}

static int g_unbound;

static void bind(const char *name, void (*handler)(void), void *real, int argc) {
    u32 iat_va = find_iat_slot(name);
    u32 addr;
    if (!iat_va) {
        fprintf(stderr, "  BRIDGE: '%s' is not imported by this build\n", name);
        g_unbound++;
        return;
    }
    addr = alloc_bridge(name, handler, argc);
    if (!addr) return;
    bridges[addr - BRIDGE_BASE].iat_va = iat_va;
    bridges[addr - BRIDGE_BASE].real   = real;
    MEM32(iat_va) = addr;
}

/* Report any import we never bridged: it would dispatch to nothing at runtime. */
static void report_unbridged(void) {
    u32 nt = NEP_IMAGE_BASE + MEM32(NEP_IMAGE_BASE + 0x3C);
    u32 imports = MEM32(nt + 0x80);
    u32 desc, missing = 0;

    if (!imports) return;
    for (desc = NEP_IMAGE_BASE + imports; MEM32(desc + 12); desc += 20) {
        const char *dll = (const char *)(uintptr_t)ADDR(NEP_IMAGE_BASE + MEM32(desc + 12));
        u32 int_rva = MEM32(desc + 0), iat_rva = MEM32(desc + 16), i;
        if (!int_rva) int_rva = iat_rva;
        for (i = 0; ; i++) {
            u32 thunk = MEM32(NEP_IMAGE_BASE + int_rva + i * 4);
            u32 slot  = NEP_IMAGE_BASE + iat_rva + i * 4;
            if (!thunk) break;
            if (MEM32(slot) >= BRIDGE_BASE && MEM32(slot) < BRIDGE_BASE + (u32)num_bridges)
                continue;
            missing++;
            fprintf(stderr, "  BRIDGE: UNBRIDGED %s!%s\n", dll,
                    (const char *)(uintptr_t)ADDR(NEP_IMAGE_BASE + thunk + 2));
        }
    }
    fprintf(stderr, "  %d bridges bound, %u imports unbridged, %d names not imported\n",
            num_bridges, missing, g_unbound);
}

recomp_func_t iat_bridge_lookup(u32 target_va) {
    if (target_va >= BRIDGE_BASE && target_va < BRIDGE_BASE + (u32)num_bridges) {
        u32 idx = target_va - BRIDGE_BASE;
        g_bridge_hit = idx;
        if (g_verbose)
            fprintf(stderr, "  BRIDGE: %s (esp=0x%08X)\n", bridges[idx].name, esp);
        return bridges[idx].handler;
    }
    return NULL;
}

/* ===================================================================
 * The generic pass-through
 *
 * On x64 there is one calling convention and the CALLER cleans the stack, so
 * calling a real API through a pointer typed with MORE parameters than it takes
 * is harmless: the extras land in shadow space and registers the callee never
 * reads. That means one bridge body serves every API that only moves integers
 * and handles around -- the table below carries just the name and how many
 * dwords the game pushed, which is all the SIMULATED stack needs to unwind.
 *
 * Argument values pass straight through: the image is mapped at its real VA, so
 * a 32-bit pointer the game holds already is a valid host pointer.
 *
 * USER and GDI handles survive the round trip to 32 bits -- Windows guarantees
 * that for WOW64. Anything returning a real pointer does not, and is not in
 * this table.
 * =================================================================== */

typedef u64 (*fnany_t)(u64, u64, u64, u64, u64, u64, u64, u64, u64, u64, u64, u64);

static void generic_bridge(void) {
    bridge_entry_t *b = &bridges[g_bridge_hit];
    u64 a[12];
    int i;
    for (i = 0; i < 12; i++) a[i] = ARG(i + 1);
    eax = (u32)((fnany_t)b->real)(a[0], a[1], a[2], a[3], a[4], a[5],
                                  a[6], a[7], a[8], a[9], a[10], a[11]);
    esp += 4 + (u32)b->argc * 4;
}

/* Everything the game imports that is answered by simply doing it for real. */
static const struct { const char *dll, *name; int argc; } g_passthrough[] = {
    /* --- GDI32 --- */
    {"gdi32",  "CreateBitmap",             5},
    {"gdi32",  "CreateFontIndirectA",      1},
    {"gdi32",  "CreatePalette",            1},
    {"gdi32",  "DeleteDC",                 1},
    {"gdi32",  "DeleteObject",             1},
    {"gdi32",  "GetDeviceCaps",            2},
    {"gdi32",  "GetStockObject",           1},
    {"gdi32",  "GetSystemPaletteEntries",  4},
    {"gdi32",  "GetSystemPaletteUse",      1},
    {"gdi32",  "GetTextExtentPointA",      4},
    {"gdi32",  "GetTextMetricsA",          2},
    {"gdi32",  "RealizePalette",           1},
    {"gdi32",  "SelectObject",             2},
    {"gdi32",  "SelectPalette",            3},
    {"gdi32",  "SetBkMode",                2},
    {"gdi32",  "SetSystemPaletteUse",      2},
    {"gdi32",  "SetTextColor",             2},
    {"gdi32",  "TextOutA",                 5},

    /* --- USER32 --- */
    {"user32", "AppendMenuA",              4},
    {"user32", "CreateMenu",               0},
    {"user32", "CreatePopupMenu",          0},
    {"user32", "DefWindowProcA",           4},
    {"user32", "DestroyCursor",            1},
    {"user32", "DestroyMenu",              1},
    {"user32", "DrawMenuBar",              1},
    {"user32", "EnableMenuItem",           3},
    {"user32", "EndDialog",                2},
    {"user32", "FillRect",                 3},
    {"user32", "FindWindowA",              2},
    {"user32", "GetClientRect",            2},
    {"user32", "GetCursorPos",             1},
    {"user32", "GetDC",                    1},
    {"user32", "GetDesktopWindow",         0},
    {"user32", "GetMenu",                  1},
    {"user32", "GetSysColor",              1},
    {"user32", "GetSystemMetrics",         1},
    {"user32", "GetWindowRect",            2},
    {"user32", "IntersectRect",            3},
    {"user32", "InvalidateRect",           3},
    {"user32", "IsDlgButtonChecked",       2},
    {"user32", "IsIconic",                 1},
    {"user32", "LoadCursorA",              2},
    {"user32", "LoadIconA",                2},
    {"user32", "MoveWindow",               5},
    {"user32", "OffsetRect",               3},
    {"user32", "PostQuitMessage",          1},
    {"user32", "ReleaseDC",                2},
    {"user32", "ScreenToClient",           2},
    {"user32", "SendMessageA",             4},
    {"user32", "SetActiveWindow",          1},
    {"user32", "SetCursor",                1},
    {"user32", "SetFocus",                 1},
    {"user32", "SetForegroundWindow",      1},
    {"user32", "SetMenu",                  2},
    {"user32", "SetRect",                  5},
    {"user32", "SetSysColors",             3},
    {"user32", "ShowWindow",               2},
    {"user32", "UpdateWindow",             1},

    /* --- KERNEL32 --- */
    {"kernel32", "CloseHandle",            1},
    {"kernel32", "CreateDirectoryA",       2},
    {"kernel32", "CreateSemaphoreA",       4},
    {"kernel32", "FileTimeToSystemTime",   2},
    {"kernel32", "FindClose",              1},
    {"kernel32", "GetCurrentDirectoryA",   2},
    {"kernel32", "GetCurrentThreadId",     0},
    {"kernel32", "GetDriveTypeA",          1},
    {"kernel32", "GetFileType",            1},
    {"kernel32", "GetFullPathNameA",       4},
    {"kernel32", "GetLastError",           0},
    {"kernel32", "GetLocalTime",           1},
    {"kernel32", "GetStdHandle",           1},
    {"kernel32", "GetTimeZoneInformation", 1},
    {"kernel32", "GetVersion",             0},
    {"kernel32", "GetWindowsDirectoryA",   2},
    {"kernel32", "ReadFile",               5},
    {"kernel32", "SetFilePointer",         4},
    {"kernel32", "SetHandleCount",         1},
    {"kernel32", "WriteFile",              5},
    {"kernel32", "WritePrivateProfileStringA", 4},
    {"kernel32", "_lclose",                1},
    {"kernel32", "_llseek",                3},
    {"kernel32", "_lread",                 3},
    {"kernel32", "lstrcatA",               2},
    {"kernel32", "lstrcmpA",               2},
    {"kernel32", "lstrcpyA",               2},
    {"kernel32", "lstrlenA",               1},

    /* --- WINMM --- */
    {"winmm",  "midiOutGetDevCapsA",       3},
    {"winmm",  "timeBeginPeriod",          1},
    {"winmm",  "timeEndPeriod",            1},
    {"winmm",  "timeGetTime",              0},
    {"winmm",  "waveOutClose",             1},
    {"winmm",  "waveOutGetNumDevs",        0},
    {"winmm",  "waveOutReset",             1},
};

/* ===================================================================
 * Memory: served from the runtime's low heap, never from the host's
 * =================================================================== */

/* GMEM_MOVEABLE hands back a "handle"; the game then GlobalLocks it for the
 * pointer. ponytail: handle == pointer, which is what Win32 does for anything
 * not allocated GMEM_DDESHARE, so Lock and Unlock are near no-ops. */
static void bridge_GlobalAlloc(void)   { eax = nep_heap_alloc(ARG(2)); esp += 4 + 8; }
static void bridge_GlobalFree(void)    { nep_heap_free(ARG(1)); eax = 0; esp += 4 + 4; }
static void bridge_GlobalLock(void)    { eax = ARG(1); esp += 4 + 4; }
static void bridge_GlobalUnlock(void)  { eax = 0; esp += 4 + 4; }
static void bridge_GlobalHandle(void)  { eax = ARG(1); esp += 4 + 4; }
static void bridge_GlobalCompact(void) { eax = 0x00400000u; esp += 4 + 4; }  /* "plenty free" */

static void bridge_VirtualAlloc(void) {
    /* The CRT reserves a region and then commits pages inside it one at a time.
     * Our heap commits everything up front, so a request naming an address we
     * already own is answered with that same address. */
    if (ARG(1) && nep_heap_owns(ARG(1))) eax = ARG(1);
    else                                 eax = nep_heap_alloc(ARG(2));
    esp += 4 + 16;
}
static void bridge_VirtualFree(void) { nep_heap_free(ARG(1)); eax = 1; esp += 4 + 12; }

/*
 * Which files the game reaches for, and whether it got them. "Data file
 * missing" says nothing about WHICH data file; this does.
 */
static int g_file_trace = -1;
static int file_trace(void) {
    if (g_file_trace < 0)
        g_file_trace = GetEnvironmentVariableA("NEP_QUIET_FILES", NULL, 0) ? 0 : 1;
    return g_file_trace;
}
static void report_file(const char *api, const char *path, int ok) {
    if (file_trace())
        fprintf(stderr, "  FILE: %-20s %s%s\n", api, path, ok ? "" : "   <-- FAILED");
}

static void bridge_lopen(void) {
    const char *path = (const char *)(uintptr_t)ADDR(ARG(1));
    HFILE f = _lopen(path, (int)ARG(2));
    report_file("_lopen", path, f != HFILE_ERROR);
    eax = (u32)f;
    esp += 4 + 8;
}

static void bridge_CreateFileA(void) {
    const char *path = (const char *)(uintptr_t)ADDR(ARG(1));
    HANDLE h = CreateFileA(path, ARG(2), ARG(3),
                           ARG(4) ? (LPSECURITY_ATTRIBUTES)(uintptr_t)ADDR(ARG(4)) : NULL,
                           ARG(5), ARG(6), (HANDLE)(uintptr_t)ARG(7));
    report_file("CreateFileA", path, h != INVALID_HANDLE_VALUE);
    eax = (u32)(uintptr_t)h;
    esp += 4 + 28;
}

static void bridge_GetFileAttributesA(void) {
    const char *path = (const char *)(uintptr_t)ADDR(ARG(1));
    DWORD a = GetFileAttributesA(path);
    report_file("GetFileAttributesA", path, a != INVALID_FILE_ATTRIBUTES);
    eax = a;
    esp += 4 + 4;
}

extern char g_game_module_path[];

static void bridge_FindFirstFileA(void) {
    const char *pat = (const char *)(uintptr_t)ADDR(ARG(1));
    HANDLE h = FindFirstFileA(pat, (WIN32_FIND_DATAA *)(uintptr_t)ADDR(ARG(2)));
    report_file("FindFirstFileA", pat, h != INVALID_HANDLE_VALUE);
    eax = (u32)(uintptr_t)h;
    esp += 4 + 8;
}

/*
 * A bare .INI name resolves against the Windows directory, which is where the
 * installer would have put ONWINCD.INI. There is a copy of it next to the game
 * on the disc, so look there too rather than silently taking defaults.
 */
static void bridge_GetPrivateProfileStringA(void) {
    const char *sec  = ARG(1) ? (const char *)(uintptr_t)ADDR(ARG(1)) : NULL;
    const char *key  = ARG(2) ? (const char *)(uintptr_t)ADDR(ARG(2)) : NULL;
    const char *def  = ARG(3) ? (const char *)(uintptr_t)ADDR(ARG(3)) : "";
    char *out        = (char *)(uintptr_t)ADDR(ARG(4));
    const char *file = ARG(6) ? (const char *)(uintptr_t)ADDR(ARG(6)) : NULL;

    eax = GetPrivateProfileStringA(sec, key, def, out, ARG(5), file);

    /*
     * CDDrive is where the game looks for its data, and the .INI on the disc
     * still holds the pre-install placeholder. The disc IS wherever the copy we
     * were pointed at lives, so answer with that instead of making everyone
     * hand-edit a file inside original/.
     */
    if (key && _stricmp(key, "CDDrive") == 0) {
        char dir[MAX_PATH];
        char *slash;
        strncpy(dir, g_game_module_path, sizeof(dir) - 1);
        dir[sizeof(dir) - 1] = 0;
        slash = strrchr(dir, '\\');
        if (slash && (u32)(slash - dir) + 2 < ARG(5)) {
            slash[1] = 0;
            strcpy(out, dir);
            eax = (u32)strlen(out);
        } else {
            fprintf(stderr, "  INI:  CDDrive override wants %u bytes, game gave %u\n",
                    slash ? (u32)(slash - dir) + 2 : 0, ARG(5));
        }
    }

    /*
     * The two environment checks the game refuses to start without, both of
     * which are asking about a machine from 1996:
     *
     *   CheckSound   opens C:\WINDOWS\SYSTEM\MIDIMAP.CFG, the Windows 3.1 MIDI
     *                mapper config, which no Windows has shipped in decades.
     *   CheckDisplay wants the desktop in 640x480 at 256 colours.
     *
     * Both are the game's own INI switches, meant to be turned off by anyone
     * whose machine did not match -- which now means everyone. They gate the
     * checks, not the sound or the graphics.
     */
    if (key && ARG(5) > 5 &&
        (_stricmp(key, "CheckSound") == 0 || _stricmp(key, "CheckDisplay") == 0)) {
        strcpy(out, "FALSE");
        eax = 5;
    }
    if (file_trace())
        fprintf(stderr, "  INI:  [%s] %s = '%s'   (%s)\n",
                sec ? sec : "?", key ? key : "?", out, file ? file : "?");
    esp += 4 + 24;
}

/*
 * The GAME's module path, not the host's. It appends ONWINCD.INI to this to
 * find its settings, and the .INI sits next to ONWIN32.EXE on the disc.
 */
static void bridge_GetModuleFileNameA(void) {
    char *out = (char *)(uintptr_t)ADDR(ARG(2));
    u32 cch = ARG(3);
    u32 n = (u32)strlen(g_game_module_path);
    if (n > cch - 1) n = cch - 1;
    memcpy(out, g_game_module_path, n);
    out[n] = 0;
    eax = n;
    esp += 4 + 12;
}

/* ===================================================================
 * Process and CRT startup
 * =================================================================== */

static void bridge_GetCommandLineA(void) {
    static u32 va = 0;
    if (!va) va = recomp_scratch_str(GetCommandLineA());
    eax = va;
    esp += 4;
}

static void bridge_GetEnvironmentStrings(void) {
    /* An empty block: two NULs. The CRT walks it and finds nothing, which is
     * true enough -- the game reads no environment variables. */
    static u32 va = 0;
    if (!va) { va = recomp_scratch_alloc(4); MEM32(va) = 0; }
    eax = va;
    esp += 4;
}

static void bridge_GetStartupInfoA(void) {
    /* STARTUPINFOA is 68 bytes on 32-bit and 104 on 64-bit, so it is filled in
     * by hand rather than passed through. The CRT reads cb, dwFlags and
     * wShowWindow; the rest being zero is what a plain launch looks like. */
    u32 p = ARG(1);
    memset((void *)(uintptr_t)ADDR(p), 0, 68);
    MEM32(p + 0)  = 68;                 /* cb */
    MEM32(p + 44) = 0;                  /* dwFlags */
    esp += 4 + 4;
}

static void bridge_GetModuleHandleA(void) {
    /*
     * The HOST's module handle, not the image base. It is only ever used as an
     * hInstance, and USER32 checks that the value a window is created with is
     * the one its class was registered with -- so both sides have to agree on
     * something USER32 recognises. This exe is linked at 0x70000000 precisely so
     * that its real handle still fits in eax.
     *
     * Resource lookups ignore the handle: FindResourceA below always reads the
     * mapped original.
     */
    eax = (u32)(uintptr_t)GetModuleHandleA(
              ARG(1) ? (const char *)(uintptr_t)ADDR(ARG(1)) : NULL);
    esp += 4 + 4;
}

static void bridge_ExitProcess(void) {
    fprintf(stderr, "\nExitProcess(0x%X)\n", ARG(1));
    recomp_dump_trace("ExitProcess");
    fflush(NULL);
    /* The real API, not the CRT's exit(): exit() would unwind host static
     * teardown while a lifted frame is still on the host stack with esp
     * pointing into the simulated one. */
    ExitProcess(ARG(1));
}

static void bridge_RaiseException(void)             { fprintf(stderr, "    RaiseException(0x%X)\n", ARG(1)); esp += 4 + 16; }
static void bridge_RtlUnwind(void)                  { esp += 4 + 16; }
static void bridge_UnhandledExceptionFilter(void)   { eax = EXCEPTION_EXECUTE_HANDLER; esp += 4 + 4; }
static void bridge_SetConsoleCtrlHandler(void)      { eax = 1; esp += 4 + 8; }

/* ===================================================================
 * WinG
 *
 * WING32.DLL was Microsoft's 1994 fast-DIB library, and it is how this game
 * draws: it creates a memory DC, asks WinG for a bitmap, gets a raw pointer to
 * the pixels, renders into that with its own code, and blits once per frame.
 * Nothing else in the import table touches pixels.
 *
 * Windows dropped WinG long ago, so the shim below is the renderer. It is also
 * why the drawing has a real chance of being correct on the first run: the game
 * writes the pixels itself, and all we have to do is put them on screen.
 * =================================================================== */

static u32   g_wing_bits;        /* low-VA framebuffer the game draws into */
static int   g_wing_w, g_wing_h;
static HDC   g_wing_dc;
static u32   g_wing_pal[256];
static BITMAPINFO *g_wing_bmi;   /* header + 256 palette entries */

static void wing_ensure_bmi(void) {
    if (g_wing_bmi) return;
    g_wing_bmi = (BITMAPINFO *)calloc(1, sizeof(BITMAPINFOHEADER) + 256 * sizeof(RGBQUAD));
    g_wing_bmi->bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    g_wing_bmi->bmiHeader.biPlanes = 1;
    g_wing_bmi->bmiHeader.biBitCount = 8;
    g_wing_bmi->bmiHeader.biCompression = BI_RGB;
}

/* WinGCreateDC(void) -> HDC */
static void bridge_WinGCreateDC(void) {
    if (!g_wing_dc) g_wing_dc = CreateCompatibleDC(NULL);
    eax = (u32)(uintptr_t)g_wing_dc;
    esp += 4;
}

/* WinGRecommendDIBFormat(BITMAPINFO*) -> BOOL. Top-down 8bpp is what the game
 * gets on every machine, so the answer never varies. */
static void bridge_WinGRecommendDIBFormat(void) {
    u32 p = ARG(1);
    memset((void *)(uintptr_t)ADDR(p), 0, sizeof(BITMAPINFOHEADER));
    MEM32(p + 0)  = sizeof(BITMAPINFOHEADER);   /* biSize */
    MEM32(p + 8)  = (u32)-1;                    /* biHeight: -1 == top-down */
    MEM16(p + 12) = 1;                          /* biPlanes */
    MEM16(p + 14) = 8;                          /* biBitCount */
    MEM32(p + 16) = BI_RGB;
    eax = 1;
    esp += 4 + 4;
}

/* WinGCreateBitmap(HDC, BITMAPINFO*, void**) -> HBITMAP
 * The third argument is where WinG writes the pixel pointer. It has to be a
 * 32-bit address the game can dereference, so the framebuffer comes out of the
 * low heap rather than from CreateDIBSection. */
static void bridge_WinGCreateBitmap(void) {
    u32 bmi = ARG(2), ppbits = ARG(3);
    int w = (int)MEM32(bmi + 4);
    int h = (int)MEM32(bmi + 8);
    if (h < 0) h = -h;
    if (w <= 0 || h <= 0) { w = 640; h = 480; }

    if (g_wing_bits) nep_heap_free(g_wing_bits);
    g_wing_w = w; g_wing_h = h;
    g_wing_bits = nep_heap_alloc((u32)(((w + 3) & ~3) * h));
    if (ppbits) MEM32(ppbits) = g_wing_bits;

    fprintf(stderr, "    WinG: %dx%d framebuffer at 0x%08X\n", w, h, g_wing_bits);
    eax = g_wing_bits;   /* the "HBITMAP" -- only ever handed back to us */
    esp += 4 + 12;
}

static void bridge_WinGGetDIBPointer(void) { eax = g_wing_bits; esp += 4 + 8; }

/* WinGSetDIBColorTable(HDC, UINT start, UINT n, RGBQUAD*) -> UINT */
static void bridge_WinGSetDIBColorTable(void) {
    u32 start = ARG(2), n = ARG(3), src = ARG(4), i;
    for (i = 0; i < n && start + i < 256; i++)
        g_wing_pal[start + i] = MEM32(src + i * 4);
    eax = n;
    esp += 4 + 16;
}

static void bridge_WinGGetDIBColorTable(void) {
    u32 start = ARG(2), n = ARG(3), dst = ARG(4), i;
    for (i = 0; i < n && start + i < 256; i++)
        MEM32(dst + i * 4) = g_wing_pal[start + i];
    eax = n;
    esp += 4 + 16;
}

static void wing_blit(HDC dst, int dx, int dy, int w, int h, int sx, int sy, int sw, int sh) {
    if (!g_wing_bits || !dst) return;
    wing_ensure_bmi();
    g_wing_bmi->bmiHeader.biWidth  = g_wing_w;
    g_wing_bmi->bmiHeader.biHeight = -g_wing_h;          /* top-down */
    memcpy(g_wing_bmi->bmiColors, g_wing_pal, sizeof(g_wing_pal));
    SetStretchBltMode(dst, COLORONCOLOR);
    StretchDIBits(dst, dx, dy, w, h, sx, sy, sw, sh,
                  (const void *)(uintptr_t)ADDR(g_wing_bits),
                  g_wing_bmi, DIB_RGB_COLORS, SRCCOPY);
}

/* WinGBitBlt(HDC dst, int x, int y, int w, int h, HDC src, int sx, int sy) */
static void bridge_WinGBitBlt(void) {
    wing_blit((HDC)(uintptr_t)ARG(1), (int)ARG(2), (int)ARG(3), (int)ARG(4), (int)ARG(5),
              (int)ARG(7), (int)ARG(8), (int)ARG(4), (int)ARG(5));
    eax = 1;
    esp += 4 + 32;
}

/* WinGStretchBlt(HDC dst,int x,int y,int w,int h, HDC src,int sx,int sy,int sw,int sh) */
static void bridge_WinGStretchBlt(void) {
    wing_blit((HDC)(uintptr_t)ARG(1), (int)ARG(2), (int)ARG(3), (int)ARG(4), (int)ARG(5),
              (int)ARG(7), (int)ARG(8), (int)ARG(9), (int)ARG(10));
    eax = 1;
    esp += 4 + 40;
}

/* ===================================================================
 * LoadLibrary / GetProcAddress
 *
 * Two kinds of module get loaded at runtime, and neither can go to the host.
 * WING32.DLL does not exist any more; NEP256.DLL and friends are 16-bit NE
 * modules, which a 32-bit process could not load on NT either -- which is why
 * this build also imports the _lopen/_lread family. Failing the load is
 * therefore the historically accurate answer, and should send the game down
 * its own fallback path.
 * =================================================================== */

#define WING_HMODULE 0x571E0000u

static void bridge_LoadLibraryA(void) {
    const char *dll = (const char *)(uintptr_t)ADDR(ARG(1));
    if (_stricmp(dll, "WING32.DLL") == 0) {
        eax = WING_HMODULE;
    } else {
        eax = 0;    /* an NE resource DLL: let the game fall back to _lopen */
    }
    fprintf(stderr, "    LoadLibraryA('%s') -> 0x%X\n", dll, eax);
    esp += 4 + 4;
}

static void bridge_FreeLibrary(void) { eax = 1; esp += 4 + 4; }

static const struct { const char *name; void (*fn)(void); int argc; } g_wing_exports[] = {
    {"WinGCreateDC",           bridge_WinGCreateDC,           0},
    {"WinGRecommendDIBFormat", bridge_WinGRecommendDIBFormat, 1},
    {"WinGCreateBitmap",       bridge_WinGCreateBitmap,       3},
    {"WinGGetDIBPointer",      bridge_WinGGetDIBPointer,      2},
    {"WinGGetDIBColorTable",   bridge_WinGGetDIBColorTable,   4},
    {"WinGSetDIBColorTable",   bridge_WinGSetDIBColorTable,   4},
    {"WinGBitBlt",             bridge_WinGBitBlt,             8},
    {"WinGStretchBlt",         bridge_WinGStretchBlt,        10},
};

static void bridge_GetProcAddress(void) {
    const char *name = (const char *)(uintptr_t)ADDR(ARG(2));
    size_t i;
    eax = 0;
    if (ARG(1) == WING_HMODULE) {
        for (i = 0; i < sizeof(g_wing_exports) / sizeof(g_wing_exports[0]); i++) {
            if (strcmp(name, g_wing_exports[i].name) == 0) {
                eax = alloc_bridge(g_wing_exports[i].name, g_wing_exports[i].fn,
                                   g_wing_exports[i].argc);
                break;
            }
        }
    }
    fprintf(stderr, "    GetProcAddress(0x%X, '%s') -> 0x%X\n", ARG(1), name, eax);
    esp += 4 + 8;
}

/* ===================================================================
 * The image's own resources
 *
 * The first run put up a MessageBox with nothing in it, because the text comes
 * from LoadStringA and LoadStringA was a stub. The game never really becomes a
 * module here -- we mapped its sections ourselves -- so the host cannot answer
 * these, and the resource directory is walked in the mapped image instead.
 *
 * Three levels: type -> name -> language, each an IMAGE_RESOURCE_DIRECTORY of
 * 16 bytes followed by 8-byte entries, high bit of the name meaning "string"
 * and high bit of the offset meaning "subdirectory".
 * =================================================================== */

static u32 res_root(void) {
    u32 nt = NEP_IMAGE_BASE + MEM32(NEP_IMAGE_BASE + 0x3C);
    u32 rva = MEM32(nt + 0x88);            /* DataDirectory[2] == RESOURCE */
    return rva ? NEP_IMAGE_BASE + rva : 0;
}

/* Compare a directory entry's name against what was asked for. `want` is either
 * an integer id (MAKEINTRESOURCE, < 0x10000) or a VA of an ANSI string; entry
 * names in the image are UTF-16 with a leading length word. */
static int res_name_match(u32 root, u32 entry_name, u32 want) {
    if (!(entry_name & 0x80000000u))            /* entry is an id */
        return want < 0x10000u && entry_name == want;
    if (want < 0x10000u) return 0;              /* id asked for, name found */
    {
        u32 p = root + (entry_name & 0x7FFFFFFFu);
        u32 n = MEM16(p), i;
        const char *w = (const char *)(uintptr_t)ADDR(want);
        for (i = 0; i < n; i++) {
            u16 c = MEM16(p + 2 + i * 2);
            char a = w[i];
            if (!a) return 0;
            if (c >= 'a' && c <= 'z') c = (u16)(c - 32);   /* resource names are case-insensitive */
            if (a >= 'a' && a <= 'z') a = (char)(a - 32);
            if (c != (u16)(unsigned char)a) return 0;
        }
        return w[n] == 0;
    }
}

/* Walk one directory looking for `want`; returns the entry's offset field. */
static u32 res_find_entry(u32 root, u32 dir, u32 want, int any) {
    u32 named = MEM16(dir + 12), ids = MEM16(dir + 14), i, n = named + ids;
    for (i = 0; i < n; i++) {
        u32 e = dir + 16 + i * 8;
        if (any || res_name_match(root, MEM32(e), want))
            return MEM32(e + 4);
    }
    return 0;
}

/* Returns the VA of the IMAGE_RESOURCE_DATA_ENTRY, or 0. */
static u32 res_find(u32 type, u32 name) {
    u32 root = res_root(), off;
    if (!root) return 0;
    off = res_find_entry(root, root, type, 0);
    if (!(off & 0x80000000u)) return 0;
    off = res_find_entry(root, root + (off & 0x7FFFFFFFu), name, 0);
    if (!(off & 0x80000000u)) return 0;
    off = res_find_entry(root, root + (off & 0x7FFFFFFFu), 0, 1);   /* first language */
    if (off & 0x80000000u) return 0;
    return root + off;
}

static void bridge_FindResourceA(void) {
    eax = res_find(ARG(3), ARG(2));
    if (!eax) fprintf(stderr, "    FindResourceA(type=0x%X, name=0x%X) -> not found\n", ARG(3), ARG(2));
    esp += 4 + 12;
}
static void bridge_LoadResource(void) {
    eax = ARG(2) ? NEP_IMAGE_BASE + MEM32(ARG(2)) : 0;   /* OffsetToData is an RVA */
    esp += 4 + 8;
}
static void bridge_LockResource(void) { eax = ARG(1); esp += 4 + 4; }
static void bridge_FreeResource(void) { eax = 0; esp += 4 + 4; }

/*
 * String tables come in bundles of sixteen under RT_STRING, keyed (id/16)+1,
 * each entry a length word followed by that many UTF-16 characters.
 */
static void bridge_LoadStringA(void) {
    u32 id = ARG(2), buf = ARG(3), cch = ARG(4);
    u32 ent = res_find(6 /* RT_STRING */, id / 16 + 1);
    u32 p, i, n;

    eax = 0;
    if (buf && cch) MEM8(buf) = 0;
    if (!ent || !buf || !cch) { esp += 4 + 16; return; }

    p = NEP_IMAGE_BASE + MEM32(ent);
    for (i = 0; i < id % 16; i++) p += 2 + MEM16(p) * 2;
    n = MEM16(p);
    if (n > cch - 1) n = cch - 1;
    for (i = 0; i < n; i++) MEM8(buf + i) = (u8)MEM16(p + 2 + i * 2);
    MEM8(buf + n) = 0;
    eax = n;
    esp += 4 + 16;
}

/* Worth seeing on the console as well as on screen: a message box is where this
 * game says why it will not start, and it blocks until someone clicks it. */
static void bridge_MessageBoxA(void) {
    const char *text = ARG(2) ? (const char *)(uintptr_t)ADDR(ARG(2)) : "";
    const char *cap  = ARG(3) ? (const char *)(uintptr_t)ADDR(ARG(3)) : "";
    fprintf(stderr, "\n*** MessageBox [%s]: %s\n\n", cap, text);
    fflush(stderr);
    if (GetEnvironmentVariableA("NEP_NO_DIALOGS", NULL, 0)) eax = IDOK;
    else eax = MessageBoxA((HWND)(uintptr_t)ARG(1), text, cap, ARG(4));
    esp += 4 + 16;
}

/* ===================================================================
 * Callbacks and structures that differ between 32- and 64-bit
 * =================================================================== */

/* The game's window procedure, as a VA into lifted code. */
static u32 g_lifted_wndproc;

static LRESULT CALLBACK nep_wndproc(HWND h, UINT m, WPARAM w, LPARAM l) {
    recomp_func_t fn;
    if (!g_lifted_wndproc) return DefWindowProcA(h, m, w, l);
    fn = recomp_lookup(g_lifted_wndproc);
    if (!fn) {
        fprintf(stderr, "    wndproc 0x%08X was not lifted\n", g_lifted_wndproc);
        return DefWindowProcA(h, m, w, l);
    }
    /* stdcall, right to left: the callee pops all four. */
    PUSH32(esp, (u32)l);
    PUSH32(esp, (u32)w);
    PUSH32(esp, (u32)m);
    PUSH32(esp, (u32)(uintptr_t)h);
    PUSH32(esp, RECOMP_RETADDR);
    fn();
    return (LRESULT)(LONG)eax;
}

/* WNDCLASSA is ten 4-byte fields in the game and ten pointer-or-int fields
 * here, so it is copied across by hand -- and lpfnWndProc is replaced, because
 * the game's is a VA with no machine code behind it. */
static void bridge_RegisterClassA(void) {
    u32 p = ARG(1);
    WNDCLASSA wc;
    memset(&wc, 0, sizeof(wc));
    wc.style         = MEM32(p + 0);
    g_lifted_wndproc = MEM32(p + 4);
    wc.lpfnWndProc   = nep_wndproc;
    wc.cbClsExtra    = (int)MEM32(p + 8);
    wc.cbWndExtra    = (int)MEM32(p + 12);
    wc.hInstance     = (HINSTANCE)(uintptr_t)MEM32(p + 16);
    wc.hIcon         = (HICON)(uintptr_t)MEM32(p + 20);
    wc.hCursor       = (HCURSOR)(uintptr_t)MEM32(p + 24);
    wc.hbrBackground = (HBRUSH)(uintptr_t)MEM32(p + 28);
    wc.lpszMenuName  = MEM32(p + 32) ? (LPCSTR)(uintptr_t)ADDR(MEM32(p + 32)) : NULL;
    wc.lpszClassName = MEM32(p + 36) ? (LPCSTR)(uintptr_t)ADDR(MEM32(p + 36)) : NULL;

    eax = RegisterClassA(&wc);
    fprintf(stderr, "    RegisterClassA('%s') wndproc=0x%08X -> 0x%X\n",
            wc.lpszClassName ? wc.lpszClassName : "(null)", g_lifted_wndproc, eax);
    esp += 4 + 4;
}

static void bridge_CreateWindowExA(void) {
    const char *cls  = ARG(2) > 0xFFFF ? (const char *)(uintptr_t)ADDR(ARG(2)) : "(atom)";
    const char *name = ARG(3) ? (const char *)(uintptr_t)ADDR(ARG(3)) : NULL;
    HWND h = CreateWindowExA(ARG(1),
                             ARG(2) > 0xFFFF ? (LPCSTR)(uintptr_t)ADDR(ARG(2)) : (LPCSTR)(uintptr_t)ARG(2),
                             name, ARG(4),
                             (int)ARG(5), (int)ARG(6), (int)ARG(7), (int)ARG(8),
                             (HWND)(uintptr_t)ARG(9), (HMENU)(uintptr_t)ARG(10),
                             (HINSTANCE)(uintptr_t)ARG(11), (void *)(uintptr_t)ARG(12));
    if (!h)
        fprintf(stderr, "    CreateWindowExA('%s', style=0x%X, %dx%d at %d,%d, hInst=0x%X) FAILED (%lu)\n",
                cls, ARG(4), (int)ARG(7), (int)ARG(8), (int)ARG(5), (int)ARG(6),
                ARG(11), GetLastError());
    else
        fprintf(stderr, "    CreateWindowExA('%s') -> 0x%08X\n", cls, (u32)(uintptr_t)h);
    eax = (u32)(uintptr_t)h;
    esp += 4 + 48;
}

/* MSG: 28 bytes in the game, 48 here. */
static void msg_to_game(const MSG *m, u32 p) {
    MEM32(p +  0) = (u32)(uintptr_t)m->hwnd;
    MEM32(p +  4) = m->message;
    MEM32(p +  8) = (u32)m->wParam;
    MEM32(p + 12) = (u32)m->lParam;
    MEM32(p + 16) = m->time;
    MEM32(p + 20) = (u32)m->pt.x;
    MEM32(p + 24) = (u32)m->pt.y;
}

static void msg_from_game(u32 p, MSG *m) {
    memset(m, 0, sizeof(*m));
    m->hwnd    = (HWND)(uintptr_t)MEM32(p + 0);
    m->message = MEM32(p + 4);
    m->wParam  = MEM32(p + 8);
    m->lParam  = (LONG_PTR)(LONG)MEM32(p + 12);
    m->time    = MEM32(p + 16);
    m->pt.x    = (LONG)MEM32(p + 20);
    m->pt.y    = (LONG)MEM32(p + 24);
}

static void bridge_PeekMessageA(void) {
    MSG m;
    eax = PeekMessageA(&m, (HWND)(uintptr_t)ARG(2), ARG(3), ARG(4), ARG(5));
    if (eax) msg_to_game(&m, ARG(1));
    esp += 4 + 20;
}

static void bridge_TranslateMessage(void) {
    MSG m; msg_from_game(ARG(1), &m);
    eax = TranslateMessage(&m);
    esp += 4 + 4;
}

static void bridge_DispatchMessageA(void) {
    MSG m; msg_from_game(ARG(1), &m);
    eax = (u32)DispatchMessageA(&m);
    esp += 4 + 4;
}

/* PAINTSTRUCT: 64 bytes in the game, 72 here (hdc grew). */
static void bridge_BeginPaint(void) {
    PAINTSTRUCT ps;
    HDC dc = BeginPaint((HWND)(uintptr_t)ARG(1), &ps);
    u32 p = ARG(2);
    MEM32(p +  0) = (u32)(uintptr_t)dc;
    MEM32(p +  4) = ps.fErase;
    MEM32(p +  8) = ps.rcPaint.left;
    MEM32(p + 12) = ps.rcPaint.top;
    MEM32(p + 16) = ps.rcPaint.right;
    MEM32(p + 20) = ps.rcPaint.bottom;
    MEM32(p + 24) = ps.fRestore;
    MEM32(p + 28) = ps.fIncUpdate;
    eax = (u32)(uintptr_t)dc;
    esp += 4 + 8;
}

static void bridge_EndPaint(void) {
    PAINTSTRUCT ps;
    u32 p = ARG(2);
    memset(&ps, 0, sizeof(ps));
    ps.hdc = (HDC)(uintptr_t)MEM32(p + 0);
    eax = EndPaint((HWND)(uintptr_t)ARG(1), &ps);
    esp += 4 + 8;
}

/* Callback-taking APIs we have not needed yet. Loud, so the first run that
 * reaches one says so instead of quietly doing nothing. */
static void bridge_DialogBoxParamA(void)   { fprintf(stderr, "    DialogBoxParamA: unimplemented\n"); eax = (u32)-1; esp += 4 + 20; }
static void bridge_EnumThreadWindows(void) { fprintf(stderr, "    EnumThreadWindows: unimplemented\n"); eax = 0; esp += 4 + 12; }

/* Audio: the WAVEHDR the game hands us is 32 bytes, not the host's 48, so these
 * need translating before they can be passed through. Silent until then. */
static void bridge_waveOutOpen(void)             { fprintf(stderr, "    waveOutOpen: silent (unimplemented)\n"); eax = MMSYSERR_NODRIVER; esp += 4 + 24; }
static void bridge_waveOutPrepareHeader(void)    { eax = MMSYSERR_NODRIVER; esp += 4 + 12; }
static void bridge_waveOutUnprepareHeader(void)  { eax = MMSYSERR_NODRIVER; esp += 4 + 12; }
static void bridge_waveOutWrite(void)            { eax = MMSYSERR_NODRIVER; esp += 4 + 12; }
static void bridge_mciSendCommandA(void)         { eax = 1; esp += 4 + 16; }

/* ===================================================================
 * Wiring
 * =================================================================== */

void setup_iat_bridges(void) {
    HMODULE h;
    size_t i;

    if (GetEnvironmentVariableA("NEP_QUIET_BRIDGES", NULL, 0)) g_verbose = 0;

    for (i = 0; i < sizeof(g_passthrough) / sizeof(g_passthrough[0]); i++) {
        void *real;
        h = GetModuleHandleA(g_passthrough[i].dll);
        if (!h) h = LoadLibraryA(g_passthrough[i].dll);
        real = h ? (void *)GetProcAddress(h, g_passthrough[i].name) : NULL;
        if (!real) {
            fprintf(stderr, "  BRIDGE: host has no %s!%s\n",
                    g_passthrough[i].dll, g_passthrough[i].name);
            continue;
        }
        bind(g_passthrough[i].name, generic_bridge, real, g_passthrough[i].argc);
    }

    bind("GlobalAlloc",              bridge_GlobalAlloc,              NULL, 2);
    bind("GlobalFree",               bridge_GlobalFree,               NULL, 1);
    bind("GlobalLock",               bridge_GlobalLock,               NULL, 1);
    bind("GlobalUnlock",             bridge_GlobalUnlock,             NULL, 1);
    bind("GlobalHandle",             bridge_GlobalHandle,             NULL, 1);
    bind("GlobalCompact",            bridge_GlobalCompact,            NULL, 1);
    bind("VirtualAlloc",             bridge_VirtualAlloc,             NULL, 4);
    bind("VirtualFree",              bridge_VirtualFree,              NULL, 3);

    bind("_lopen",                   bridge_lopen,                    NULL, 2);
    bind("GetModuleFileNameA",       bridge_GetModuleFileNameA,       NULL, 3);
    bind("FindFirstFileA",           bridge_FindFirstFileA,           NULL, 2);
    bind("GetPrivateProfileStringA", bridge_GetPrivateProfileStringA, NULL, 6);
    bind("CreateFileA",              bridge_CreateFileA,              NULL, 7);
    bind("GetFileAttributesA",       bridge_GetFileAttributesA,       NULL, 1);
    bind("GetCommandLineA",          bridge_GetCommandLineA,          NULL, 0);
    bind("GetEnvironmentStrings",    bridge_GetEnvironmentStrings,    NULL, 0);
    bind("GetStartupInfoA",          bridge_GetStartupInfoA,          NULL, 1);
    bind("GetModuleHandleA",         bridge_GetModuleHandleA,         NULL, 1);
    bind("ExitProcess",              bridge_ExitProcess,              NULL, 1);
    bind("RaiseException",           bridge_RaiseException,           NULL, 4);
    bind("RtlUnwind",                bridge_RtlUnwind,                NULL, 4);
    bind("UnhandledExceptionFilter", bridge_UnhandledExceptionFilter, NULL, 1);
    bind("SetConsoleCtrlHandler",    bridge_SetConsoleCtrlHandler,    NULL, 2);

    bind("LoadLibraryA",             bridge_LoadLibraryA,             NULL, 1);
    bind("FreeLibrary",              bridge_FreeLibrary,              NULL, 1);
    bind("GetProcAddress",           bridge_GetProcAddress,           NULL, 2);

    bind("FindResourceA",            bridge_FindResourceA,            NULL, 3);
    bind("LoadResource",             bridge_LoadResource,             NULL, 2);
    bind("LockResource",             bridge_LockResource,             NULL, 1);
    bind("FreeResource",             bridge_FreeResource,             NULL, 1);
    bind("LoadStringA",              bridge_LoadStringA,              NULL, 4);
    bind("MessageBoxA",              bridge_MessageBoxA,              NULL, 4);

    bind("RegisterClassA",           bridge_RegisterClassA,           NULL, 1);
    bind("CreateWindowExA",          bridge_CreateWindowExA,          NULL, 12);
    bind("PeekMessageA",             bridge_PeekMessageA,             NULL, 5);
    bind("TranslateMessage",         bridge_TranslateMessage,         NULL, 1);
    bind("DispatchMessageA",         bridge_DispatchMessageA,         NULL, 1);
    bind("BeginPaint",               bridge_BeginPaint,               NULL, 2);
    bind("EndPaint",                 bridge_EndPaint,                 NULL, 2);
    bind("DialogBoxParamA",          bridge_DialogBoxParamA,          NULL, 5);
    bind("EnumThreadWindows",        bridge_EnumThreadWindows,        NULL, 3);

    bind("waveOutOpen",              bridge_waveOutOpen,              NULL, 6);
    bind("waveOutPrepareHeader",     bridge_waveOutPrepareHeader,     NULL, 3);
    bind("waveOutUnprepareHeader",   bridge_waveOutUnprepareHeader,   NULL, 3);
    bind("waveOutWrite",             bridge_waveOutWrite,             NULL, 3);
    bind("mciSendCommandA",          bridge_mciSendCommandA,          NULL, 4);

    report_unbridged();
}
