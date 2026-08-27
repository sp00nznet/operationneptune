#!/usr/bin/env python3
"""
TLC asset extractor
===================

Carried over verbatim from the OpenGizmos clean-room work, which cracked these
formats across the whole family. Operation Neptune (`on`) is one target of nine;
the siblings stay in because they are how the ON formats were cross-checked in
the first place -- RUND, the doubled-byte palettes and the RLE tilemaps all
appear in more than one game.

  python tools/extract_assets.py on original extracted/on --all

Extracts sprites, audio, puzzles, and game data from all supported
The Learning Company and MECC educational games (1990-1998).

Supported games:
  SSG  - Super Solvers: Gizmos & Gadgets
  ON   - Operation Neptune
  TMT  - Treasure Mountain!
  TCV  - Treasure Cove!
  TMS  - Treasure MathStorm!
  SSO  - Super Solvers: OutNumbered!
  SSR  - Super Solvers: Spellbound!
  SSB  - Super Solvers: Midnight Rescue! / Spellbound Wizards
  SBW  - Storybook Weaver Deluxe (MECC)

Usage:
  python extract_all.py <game_id> <source_path> <output_path> [--sprites] [--audio] [--puzzles] [--all]
  python extract_all.py scan <source_path>          # Auto-detect all games
  python extract_all.py all <base_path> <output>    # Extract everything from all games
"""

import struct
import os
import sys
import shutil
import argparse
import json
from pathlib import Path
from typing import Optional

# ============================================================================
# NE (New Executable) Resource Parser
# ============================================================================

DOS_MAGIC = 0x5A4D  # 'MZ'
NE_MAGIC  = 0x454E  # 'NE'

# Standard NE resource type IDs
NE_RT_CURSOR       = 0x8001
NE_RT_BITMAP       = 0x8002
NE_RT_ICON         = 0x8003
NE_RT_MENU         = 0x8004
NE_RT_DIALOG       = 0x8005
NE_RT_STRING        = 0x8006
NE_RT_FONTDIR      = 0x8007
NE_RT_FONT         = 0x8008
NE_RT_ACCELERATOR  = 0x8009
NE_RT_RCDATA       = 0x800A
NE_RT_GROUP_CURSOR = 0x800C
NE_RT_GROUP_ICON   = 0x800E

# TLC custom resource types
CUSTOM_15    = 0x800F  # Palette/animation data
CUSTOM_32513 = 0xFF01  # Sprites
CUSTOM_32514 = 0xFF02  # Sprite meta / WAV audio (SSO)
CUSTOM_32515 = 0xFF03  # Game definitions
CUSTOM_32516 = 0xFF04  # Room/level data
CUSTOM_32517 = 0xFF05  # Unknown
CUSTOM_32518 = 0xFF06  # Unknown
CUSTOM_32519 = 0xFF07  # WAV audio


def type_name(type_id):
    names = {
        NE_RT_CURSOR: "CURSOR", NE_RT_BITMAP: "BITMAP", NE_RT_ICON: "ICON",
        NE_RT_MENU: "MENU", NE_RT_DIALOG: "DIALOG", NE_RT_STRING: "STRING",
        NE_RT_FONTDIR: "FONTDIR", NE_RT_FONT: "FONT", NE_RT_ACCELERATOR: "ACCELERATOR",
        NE_RT_RCDATA: "RCDATA", NE_RT_GROUP_CURSOR: "GROUP_CURSOR",
        NE_RT_GROUP_ICON: "GROUP_ICON",
        CUSTOM_15: "CUSTOM_15", CUSTOM_32513: "CUSTOM_32513",
        CUSTOM_32514: "CUSTOM_32514", CUSTOM_32515: "CUSTOM_32515",
        CUSTOM_32516: "CUSTOM_32516", CUSTOM_32517: "CUSTOM_32517",
        CUSTOM_32518: "CUSTOM_32518", CUSTOM_32519: "CUSTOM_32519",
    }
    if type_id in names:
        return names[type_id]
    if type_id & 0x8000:
        return f"CUSTOM_{type_id & 0x7FFF}"
    return f"TYPE_{type_id}"


class NEResource:
    __slots__ = ('type_id', 'res_id', 'offset', 'size', 'flags')

    def __init__(self, type_id, res_id, offset, size, flags=0):
        self.type_id = type_id
        self.res_id = res_id
        self.offset = offset
        self.size = size
        self.flags = flags

    def __repr__(self):
        return f"<{type_name(self.type_id)} id={self.res_id} size={self.size} off=0x{self.offset:x}>"


class NEResourceExtractor:
    """Parses Windows NE (New Executable) format files (.DAT, .DLL, .RSC, .EXE)."""

    def __init__(self, path):
        self.path = path
        self.resources = []
        self._parse()

    def _parse(self):
        with open(self.path, 'rb') as f:
            # DOS header
            magic = struct.unpack('<H', f.read(2))[0]
            if magic != DOS_MAGIC:
                raise ValueError(f"Not a valid MZ executable: {self.path}")

            f.seek(0x3C)
            ne_offset = struct.unpack('<I', f.read(4))[0]

            # NE header
            f.seek(ne_offset)
            ne_magic = struct.unpack('<H', f.read(2))[0]
            if ne_magic != NE_MAGIC:
                raise ValueError(f"Not a valid NE executable: {self.path}")

            # Resource table offset (relative to NE header)
            f.seek(ne_offset + 0x24)
            res_table_rel = struct.unpack('<H', f.read(2))[0]
            res_table_offset = ne_offset + res_table_rel

            f.seek(res_table_offset)
            alignment_shift = struct.unpack('<H', f.read(2))[0]

            # Parse resource type entries
            while True:
                data = f.read(8)
                if len(data) < 8:
                    break
                type_id, count = struct.unpack('<HH', data[:4])
                # reserved 4 bytes
                if type_id == 0:
                    break

                for _ in range(count):
                    entry = f.read(12)
                    if len(entry) < 12:
                        break
                    offset_raw, length_raw, flags, res_id = struct.unpack('<HHHH', entry[:8])
                    # remaining 4 bytes are reserved

                    offset = offset_raw << alignment_shift
                    size = length_raw << alignment_shift

                    self.resources.append(NEResource(type_id, res_id, offset, size, flags))

    def list_by_type(self, type_id):
        return [r for r in self.resources if r.type_id == type_id]

    def extract(self, res):
        with open(self.path, 'rb') as f:
            f.seek(res.offset)
            return f.read(res.size)

    def extract_by_type_id(self, type_id, res_id):
        for r in self.resources:
            if r.type_id == type_id and r.res_id == res_id:
                return self.extract(r)
        return None


# ============================================================================
# Palette Handling
# ============================================================================

def load_palette_from_bmp(bmp_path):
    """Load 256-color palette from a BMP file (offset 54, 1024 bytes BGRA)."""
    with open(bmp_path, 'rb') as f:
        magic = f.read(2)
        if magic != b'BM':
            raise ValueError(f"Not a BMP file: {bmp_path}")
        f.seek(54)
        pal_data = f.read(1024)
    palette = []
    for i in range(256):
        b, g, r, a = pal_data[i*4:(i+1)*4]
        palette.append((r, g, b))
    return palette


def load_palette_from_raw(pal_path):
    """Load palette from raw file (1024 bytes BGRA, or 768 bytes RGB)."""
    data = open(pal_path, 'rb').read()
    palette = []
    if len(data) >= 1024:
        for i in range(256):
            b, g, r, a = data[i*4:(i+1)*4]
            palette.append((r, g, b))
    elif len(data) >= 768:
        for i in range(256):
            r, g, b = data[i*3:(i+1)*3]
            palette.append((r, g, b))
    else:
        raise ValueError(f"Unknown palette format (size={len(data)})")
    return palette


def load_doubled_palette(data):
    """Load TLC doubled-byte palette: 00 R 00 G 00 B × 256 = 1536 bytes."""
    palette = []
    for i in range(256):
        off = i * 6
        r = data[off + 1]
        g = data[off + 3]
        b = data[off + 5]
        palette.append((r, g, b))
    return palette


def grayscale_palette():
    """Fallback grayscale palette."""
    return [(i, i, i) for i in range(256)]


# ============================================================================
# BMP Writer
# ============================================================================

def write_bmp(path, width, height, pixels, palette):
    """Write an 8-bit indexed BMP file.

    pixels: list/bytes of palette indices, length = width*height
    palette: list of 256 (R,G,B) tuples
    """
    row_size = (width + 3) & ~3  # Rows padded to 4-byte boundary
    pixel_data_size = row_size * height
    file_header_size = 14
    info_header_size = 40
    palette_size = 256 * 4
    data_offset = file_header_size + info_header_size + palette_size
    file_size = data_offset + pixel_data_size

    with open(path, 'wb') as f:
        # BITMAPFILEHEADER
        f.write(b'BM')
        f.write(struct.pack('<I', file_size))
        f.write(struct.pack('<HH', 0, 0))
        f.write(struct.pack('<I', data_offset))

        # BITMAPINFOHEADER
        f.write(struct.pack('<I', info_header_size))
        f.write(struct.pack('<i', width))
        f.write(struct.pack('<i', height))  # positive = bottom-up
        f.write(struct.pack('<HH', 1, 8))   # planes=1, bpp=8
        f.write(struct.pack('<I', 0))        # no compression
        f.write(struct.pack('<I', pixel_data_size))
        f.write(struct.pack('<II', 0, 0))    # resolution
        f.write(struct.pack('<II', 256, 0))  # colors used, important

        # Palette (BGRA)
        for r, g, b in palette:
            f.write(struct.pack('BBBB', b, g, r, 0))

        # Pixel data (bottom-up)
        for y in range(height - 1, -1, -1):
            row_start = y * width
            row = bytes(pixels[row_start:row_start + width])
            if len(row) < width:
                row += b'\x00' * (width - len(row))
            f.write(row)
            # Pad row to 4-byte boundary
            padding = row_size - width
            if padding > 0:
                f.write(b'\x00' * padding)


# ============================================================================
# GRP Archive Parser (RGrp format - SSB/Spellbound Wizards)
# ============================================================================

GRP_MAGIC = b'RGrp'
GRP_COMPRESSION_RLE = 0x01
GRP_COMPRESSION_LZ = 0x02


class GrpArchive:
    """Parses RGrp archive files (.GRP) used by SSB/Spellbound Wizards.

    Big-endian format:
      Header (32 bytes): two 16-byte sections
        RGrp(4) + padding(4) + count(4 BE) + index_offset(4 BE)  x2
      Index entries (16 bytes each, at offset specified in header):
        tag(4) + padding(2) + resource_id(2 BE) + size(4 BE) + data_offset(4 BE)
      Tags: ASEQ (animation), WAVE (audio), LIPS/LIP3 (lip sync), RGrp (sub-archive)
    """

    def __init__(self, path):
        self.path = path
        self.entries = []  # list of dicts with tag, res_id, size, offset
        self._parse()

    def _parse(self):
        with open(self.path, 'rb') as f:
            header = f.read(32)
            if len(header) < 32:
                raise ValueError(f"File too small for GRP header: {self.path}")

            magic = header[0:4]
            if magic != GRP_MAGIC:
                raise ValueError(f"Not a GRP archive (bad magic): {self.path}")

            # Parse two sections (big-endian)
            count1 = struct.unpack('>I', header[8:12])[0]
            offset1 = struct.unpack('>I', header[12:16])[0]
            count2 = struct.unpack('>I', header[24:28])[0]
            offset2 = struct.unpack('>I', header[28:32])[0]

            file_size = f.seek(0, 2)

            # Read section 1 index entries
            if offset1 < file_size and count1 < 10000:
                self._read_index(f, offset1, count1, file_size)

            # Read section 2 index entries
            if offset2 < file_size and count2 < 10000:
                # Section 2 table may start 16 bytes after the stated offset
                self._read_index_fuzzy(f, offset2, count2, file_size)

    def _read_index(self, f, offset, count, file_size):
        f.seek(offset)
        for _ in range(count):
            entry_data = f.read(16)
            if len(entry_data) < 16:
                break
            tag = entry_data[0:4].decode('ascii', errors='replace')
            res_id = struct.unpack('>H', entry_data[6:8])[0]
            size = struct.unpack('>I', entry_data[8:12])[0]
            data_offset = struct.unpack('>I', entry_data[12:16])[0]
            if data_offset < file_size and size > 0:
                self.entries.append({
                    'tag': tag,
                    'res_id': res_id,
                    'size': size,
                    'offset': data_offset,
                })

    def _read_index_fuzzy(self, f, offset, count, file_size):
        """Try reading index at offset, or offset+16 if the first doesn't look like entries."""
        valid_tags = {b'ASEQ', b'WAVE', b'LIPS', b'LIP3', b'RGrp', b'SPRT'}
        for try_off in [offset, offset + 16]:
            if try_off >= file_size:
                continue
            f.seek(try_off)
            test = f.read(4)
            if test in valid_tags:
                f.seek(try_off)
                for _ in range(count):
                    entry_data = f.read(16)
                    if len(entry_data) < 16:
                        break
                    tag = entry_data[0:4].decode('ascii', errors='replace')
                    res_id = struct.unpack('>H', entry_data[6:8])[0]
                    size = struct.unpack('>I', entry_data[8:12])[0]
                    data_offset = struct.unpack('>I', entry_data[12:16])[0]
                    if data_offset < file_size and size > 0:
                        self.entries.append({
                            'tag': tag,
                            'res_id': res_id,
                            'size': size,
                            'offset': data_offset,
                        })
                return

    def extract_entry(self, entry):
        """Extract raw data for an entry."""
        with open(self.path, 'rb') as f:
            f.seek(entry['offset'])
            return f.read(entry['size'])

    def get_by_tag(self, tag):
        """Get all entries with a specific tag."""
        return [e for e in self.entries if e['tag'] == tag]


def extract_grp_aseq_frames(data, palette):
    """Extract individual sprite frames from ASEQ animation data.

    ASEQ data contains packed sprite frames. Each frame has a 12-byte header:
      width(2 LE) height(2 LE) hotspotX(2 LE) hotspotY(2 LE) flags(2 LE) misc(2 LE)
    Followed by width*height pixel data.

    Returns list of (width, height, pixels) tuples.
    """
    frames = []
    pos = 0
    while pos + 12 <= len(data):
        width, height = struct.unpack('<HH', data[pos:pos+4])
        if width == 0 or height == 0 or width > 2048 or height > 2048:
            pos += 2  # Try to find next valid header
            continue

        expected = width * height
        header_end = pos + 12
        if header_end + expected > len(data):
            break

        pixels = data[header_end:header_end + expected]
        frames.append((width, height, bytes(pixels)))
        pos = header_end + expected

    return frames


def extract_grp_sprites(grp_path, palette, output_dir, label=""):
    """Extract sprites from a GRP archive's ASEQ entries."""
    os.makedirs(output_dir, exist_ok=True)
    try:
        grp = GrpArchive(grp_path)
    except (ValueError, struct.error) as e:
        print(f"  [ERROR] GRP parse error: {e}")
        return 0

    count = 0
    for entry in grp.get_by_tag('ASEQ'):
        try:
            data = grp.extract_entry(entry)
            frames = extract_grp_aseq_frames(data, palette)
            for fidx, (w, h, pixels) in enumerate(frames):
                fname = f"aseq_{entry['res_id']}_f{fidx:03d}_{w}x{h}.bmp"
                write_bmp(os.path.join(output_dir, fname), w, h, pixels, palette)
                count += 1
        except Exception:
            pass

    return count


def extract_grp_audio(grp_path, output_dir):
    """Extract WAVE audio from a GRP archive."""
    os.makedirs(output_dir, exist_ok=True)
    try:
        grp = GrpArchive(grp_path)
    except (ValueError, struct.error) as e:
        print(f"  [ERROR] GRP parse error: {e}")
        return 0

    count = 0
    for entry in grp.get_by_tag('WAVE'):
        try:
            data = grp.extract_entry(entry)
            # Check if it's a RIFF WAV
            if is_wav_data(data):
                fname = f"wave_{entry['res_id']}.wav"
                with open(os.path.join(output_dir, fname), 'wb') as f:
                    f.write(data)
                count += 1
            elif is_raw_pcm_sound(data):
                wav_data = raw_pcm_to_wav(data)
                fname = f"wave_{entry['res_id']}.wav"
                with open(os.path.join(output_dir, fname), 'wb') as f:
                    f.write(wav_data)
                count += 1
            else:
                # Save raw for analysis
                fname = f"wave_{entry['res_id']}.bin"
                with open(os.path.join(output_dir, fname), 'wb') as f:
                    f.write(data)
                count += 1
        except Exception:
            pass

    return count


# ============================================================================
# Sprite Decompression
# ============================================================================

def decompress_rle_tlc(data, expected_pixels):
    """TLC RLE format: FF <byte> <count> = repeat byte count times, 00 = row end."""
    pixels = bytearray()
    i = 0
    while len(pixels) < expected_pixels and i < len(data):
        if data[i] == 0xFF and i + 2 < len(data):
            val = data[i + 1]
            count = data[i + 2]
            if count == 0:
                count = 1
            pixels.extend([val] * count)
            i += 3
        else:
            pixels.append(data[i])
            i += 1

    # Pad if needed
    while len(pixels) < expected_pixels:
        pixels.append(0)

    return bytes(pixels[:expected_pixels])


def decompress_rund(data):
    """RUND format sprites (Operation Neptune, Treasure series).

    Header: 2-byte width, 2-byte height, 4-byte 'RUND' magic
    Compression: byte >= 0x80 = RLE run, byte < 0x80 = literal run
    Returns (width, height, pixels) or None.
    """
    if len(data) < 8:
        return None

    width, height = struct.unpack('<HH', data[0:4])
    magic = data[4:8]

    if magic != b'RUND':
        return None

    if width == 0 or height == 0 or width > 2048 or height > 2048:
        return None

    expected = width * height
    pixels = bytearray()
    i = 8

    while len(pixels) < expected and i < len(data):
        b = data[i]
        i += 1
        if b >= 0x80:
            # RLE run: repeat next byte (b & 0x7F) times
            count = b & 0x7F
            if i < len(data):
                val = data[i]
                i += 1
                pixels.extend([val] * count)
        else:
            # Literal run: next b bytes are literals
            count = b
            for _ in range(count):
                if i < len(data):
                    pixels.append(data[i])
                    i += 1
                else:
                    pixels.append(0)

    while len(pixels) < expected:
        pixels.append(0)

    return width, height, bytes(pixels[:expected])


def decompress_rle_tilemap(data, width, height):
    """RLE tilemap format (Operation Neptune LABRNTH/READER resources).

    Same FF XX YY format but for full-screen 640x480 images.
    """
    expected = width * height
    pixels = bytearray()
    i = 0

    while len(pixels) < expected and i < len(data):
        if data[i] == 0xFF and i + 2 < len(data):
            val = data[i + 1]
            count = data[i + 2] + 1
            pixels.extend([val] * count)
            i += 3
        elif data[i] == 0x00:
            pixels.append(0)
            i += 1
        else:
            pixels.append(data[i])
            i += 1

    while len(pixels) < expected:
        pixels.append(0)

    return bytes(pixels[:expected])


# ============================================================================
# WAV Detection and Extraction
# ============================================================================

def is_wav_data(data):
    """Check if data starts with RIFF/WAVE header."""
    return len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WAVE'


def is_raw_pcm_sound(data):
    """Check if data is TLC raw PCM format.

    Format: 4 bytes flags (0), 4 bytes sample rate, 4 bytes data size, then PCM data.
    Data values are unsigned 8-bit centered at 0x80.
    """
    if len(data) < 16:
        return False
    flags = struct.unpack('<I', data[0:4])[0]
    sample_rate = struct.unpack('<I', data[4:8])[0]
    data_size = struct.unpack('<I', data[8:12])[0]
    # Validate: flags should be 0, sample_rate should be reasonable, data_size should fit
    return (flags == 0 and sample_rate in (8000, 11025, 16000, 22050, 44100)
            and 0 < data_size <= len(data))


def raw_pcm_to_wav(data):
    """Convert TLC raw PCM sound resource to WAV format."""
    sample_rate = struct.unpack('<I', data[4:8])[0]
    data_size = struct.unpack('<I', data[8:12])[0]
    pcm_data = data[16:16 + data_size]  # Skip 16-byte header

    # Build WAV file
    channels = 1
    bits_per_sample = 8
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    pcm_len = len(pcm_data)

    wav = bytearray()
    wav.extend(b'RIFF')
    wav.extend(struct.pack('<I', 36 + pcm_len))
    wav.extend(b'WAVE')
    wav.extend(b'fmt ')
    wav.extend(struct.pack('<I', 16))  # fmt chunk size
    wav.extend(struct.pack('<H', 1))   # PCM format
    wav.extend(struct.pack('<H', channels))
    wav.extend(struct.pack('<I', sample_rate))
    wav.extend(struct.pack('<I', byte_rate))
    wav.extend(struct.pack('<H', block_align))
    wav.extend(struct.pack('<H', bits_per_sample))
    wav.extend(b'data')
    wav.extend(struct.pack('<I', pcm_len))
    wav.extend(pcm_data)
    return bytes(wav)


def extract_wav_from_ne(ne, output_dir, type_ids=None):
    """Extract all WAV audio resources from an NE file.

    Handles both standard RIFF WAV and TLC raw PCM formats.
    Returns list of (res_id, output_path) tuples.
    """
    if type_ids is None:
        type_ids = [CUSTOM_32514, CUSTOM_32519, CUSTOM_32513]

    extracted = []
    for type_id in type_ids:
        for res in ne.list_by_type(type_id):
            data = ne.extract(res)
            wav_data = None
            if is_wav_data(data):
                wav_data = data
            elif is_raw_pcm_sound(data):
                wav_data = raw_pcm_to_wav(data)

            if wav_data:
                fname = f"{type_name(type_id)}_{res.res_id}.wav"
                out_path = os.path.join(output_dir, fname)
                with open(out_path, 'wb') as f:
                    f.write(wav_data)
                extracted.append((res.res_id, out_path))
    return extracted


def extract_wav_from_ne_all_types(ne, output_dir):
    """Try all resource types for WAV data (standard RIFF or raw PCM)."""
    extracted = []
    for res in ne.resources:
        data = ne.extract(res)
        wav_data = None
        if is_wav_data(data):
            wav_data = data
        elif is_raw_pcm_sound(data):
            wav_data = raw_pcm_to_wav(data)

        if wav_data:
            fname = f"{type_name(res.type_id)}_{res.res_id}.wav"
            out_path = os.path.join(output_dir, fname)
            with open(out_path, 'wb') as f:
                f.write(wav_data)
            extracted.append((res.res_id, out_path))
    return extracted


# ============================================================================
# Game Definitions - Source file locations for each game
# ============================================================================

GAME_DEFS = {
    'ssg': {
        'name': 'Super Solvers: Gizmos & Gadgets',
        'company': 'TLC',
        'sprite_files': {
            '256_sprites': 'SSGWINCD/GIZMO256.DAT',
            '16_sprites': 'SSGWINCD/GIZMO16.DAT',
            'puzzle_sprites_256': 'SSGWINCD/PUZ256.DAT',
            'puzzle_sprites_16': 'SSGWINCD/PUZ16.DAT',
            'auto_sprites_256': 'SSGWINCD/AUTO256.DAT',
            'auto_sprites_16': 'SSGWINCD/AUTO16.DAT',
            'plane_sprites_256': 'SSGWINCD/PLANE256.DAT',
            'plane_sprites_16': 'SSGWINCD/PLANE16.DAT',
            'ae_sprites_256': 'SSGWINCD/AE256.DAT',
            'ae_sprites_16': 'SSGWINCD/AE16.DAT',
        },
        'audio_files': {
            'main_audio': 'SSGWINCD/GIZMO.DAT',
            'gizmo_speech': 'SSGWINCD/GIZSPCH.DAT',
            'auto_speech': 'SSGWINCD/AUTOSPCH.DAT',
            'ae_speech': 'SSGWINCD/AESPCH.DAT',
            'puzzle_speech_1': 'SSGWINCD/PUZSPCH1.DAT',
            'puzzle_speech_2': 'SSGWINCD/PUZSPCH2.DAT',
            'puzzle_speech_3': 'SSGWINCD/PUZSPCH3.DAT',
            'plane_speech_1': 'SSGWINCD/PLNESP1.DAT',
            'plane_speech_2': 'SSGWINCD/PLNESP2.DAT',
        },
        'midi_dir': 'SSGWINCD/MIDI',
        'game_data': {
            'main': 'SSGWINCD/GIZMO.DAT',
            'puzzle': 'SSGWINCD/PUZZLE.DAT',
            'auto': 'SSGWINCD/AUTO.DAT',
            'plane': 'SSGWINCD/PLANE.DAT',
            'ae': 'SSGWINCD/AE.DAT',
            'font': 'SSGWINCD/FONT.DAT',
            'help': 'SSGWINCD/HELP.DAT',
        },
        'sprite_format': 'rle_tlc',
        'palette_source': 'doubled',  # doubled-byte in CUSTOM_32515
        'video_dir': None,
    },
    'on': {
        'name': 'Operation Neptune',
        'company': 'TLC',
        'sprite_files': {
            '256_sprites': 'ONWINCD/NEP256.DLL',
            'sorter': 'INSTALL/SORTER.RSC',
        },
        'audio_files': {
            'sound_bank_0': 'ONWINCD/NE0SOUND.DLL',
            'sound_bank_1': 'ONWINCD/NE1SOUND.DLL',
            'sound_bank_2': 'ONWINCD/NE2SOUND.DLL',
            'common': 'INSTALL/COMMON.RSC',
        },
        'midi_dir': 'ONWINCD/SOUNDS',
        # The .RSC files live in INSTALL/ on the retail CD; an installed copy
        # moves them next to the game. CD layout is what this repo works from.
        'game_data': {
            'main': 'ONWINCD/NEP.DLL',
            'background_1': 'ONWINCD/NEPBG1.DLL',
            'background_2': 'ONWINCD/NEPBG2.DLL',
            'sorter': 'INSTALL/SORTER.RSC',
            'labyrinth_1': 'INSTALL/LABRNTH1.RSC',
            'labyrinth_2': 'INSTALL/LABRNTH2.RSC',
            'reader_1': 'INSTALL/READER1.RSC',
            'reader_2': 'INSTALL/READER2.RSC',
            'ot3': 'INSTALL/OT3.RSC',
            'autorun': 'INSTALL/AUTORUN.RSC',
        },
        'sprite_format': 'rund',
        'palette_source': 'bmp:INSTALL/AUTO256.BMP',
        'video_dir': 'MOVIES',
    },
    'tmt': {
        'name': 'Treasure Mountain!',
        'company': 'TLC',
        'sprite_files': {
            '256_sprites': 'TMTWINCD/TMT256.DLL',
            '16_sprites': 'TMTWINCD/TMT16.DLL',
        },
        'audio_files': {
            'sound_bank_0': 'TMTWINCD/TM0SOUND.DLL',
            'sound_bank_1': 'TMTWINCD/TM1SOUND.DLL',
            'sound_bank_2': 'TMTWINCD/TM2SOUND.DLL',
            'sound_bank_3': 'TMTWINCD/TM3SOUND.DLL',
            'sound_bank_4': 'TMTWINCD/TM4SOUND.DLL',
            'sound_bank_5': 'TMTWINCD/TM5SOUND.DLL',
            'sound_bank_6': 'TMTWINCD/TM6SOUND.DLL',
            'sound_bank_7': 'TMTWINCD/TM7SOUND.DLL',
            'sound_bank_8': 'TMTWINCD/TM8SOUND.DLL',
        },
        'midi_dir': 'TMTWINCD/SOUNDS',
        'game_data': {
            'main': 'TMTWINCD/TMT.DLL',
        },
        'sprite_format': 'rund',
        'palette_source': 'runtime',  # Needs VGA capture
        'video_dir': None,
    },
    'tcv': {
        'name': 'Treasure Cove!',
        'company': 'TLC',
        'sprite_files': {
            '256_sprites': 'TCVWINCD/TCV256.DLL',
            '16_sprites': 'TCVWINCD/TCV16.DLL',
        },
        'audio_files': {
            'sound_bank_main': 'TCVWINCD/TCVSOUND.DLL',
            'sound_bank_2': 'TCVWINCD/TC2SOUND.DLL',
            'sound_bank_3': 'TCVWINCD/TC3SOUND.DLL',
            'sound_bank_4': 'TCVWINCD/TC4SOUND.DLL',
            'sound_bank_5': 'TCVWINCD/TC5SOUND.DLL',
            'sound_bank_6': 'TCVWINCD/TC6SOUND.DLL',
        },
        'midi_dir': 'TCVWINCD/SOUNDS',
        'game_data': {
            'main': 'TCVWINCD/TCV.DLL',
        },
        'sprite_format': 'rund',
        'palette_source': 'runtime',  # Needs VGA capture
        'video_dir': None,
    },
    'tms': {
        'name': 'Treasure MathStorm!',
        'company': 'TLC',
        'sprite_files': {
            'main_data': 'DATA/TMSDATA.DAT',
            'animations': 'DATA/TMSANIM.DAT',
        },
        'audio_files': {
            'sounds': 'DATA/TMSSOUND.DAT',
        },
        'midi_dir': None,  # WAV files in DATA/MUSIC/
        'wav_dir': 'DATA/MUSIC',
        'game_data': {
            'main': 'DATA/TMSDATA.DAT',
        },
        'sprite_format': 'rle_tlc',
        'palette_source': 'runtime',
        'video_dir': 'DATA',  # .SMK files
    },
    'sso': {
        'name': 'Super Solvers: OutNumbered!',
        'company': 'TLC',
        'sprite_files': {
            'main_1': 'SSOWINCD/SSO1.DAT',
            'main_2': 'SSOWINCD/SSO2.DAT',
            'main_3': 'SSOWINCD/SSO3.DAT',
        },
        'audio_files': {
            'sounds': 'SSOWINCD/SND.DAT',
            'speech': 'SSOWINCD/SPEECH.DAT',
        },
        'midi_dir': 'SSOWINCD/MIDI',
        'game_data': {
            'main_1': 'SSOWINCD/SSO1.DAT',
            'main_2': 'SSOWINCD/SSO2.DAT',
            'main_3': 'SSOWINCD/SSO3.DAT',
        },
        'sprite_format': 'unknown',  # Needs RE
        'palette_source': 'unknown',
        'video_dir': None,
    },
    'ssr': {
        'name': 'Super Solvers: Spellbound!',
        'company': 'TLC',
        'sprite_files': {
            'main': 'SSRWINCD/SSR1.DAT',
            'fb1': 'SSRWINCD/FB1.DAT',
            'fb2': 'SSRWINCD/FB2.DAT',
        },
        'audio_files': {
            'sfx': 'SSRWINCD/SFX.DAT',
            'speech': 'SSRWINCD/SPEECH.DAT',
        },
        'midi_dir': 'SSRWINCD/MIDI',
        'game_data': {
            'main': 'SSRWINCD/SSR1.DAT',
            'task': 'SSRWINCD/TASK.RSC',
        },
        'sprite_format': 'rle_tlc',
        'palette_source': 'unknown',
        'video_dir': None,
    },
    'ssb': {
        'name': 'Super Solvers: Spellbound Wizards',
        'company': 'TLC',
        'sprite_files': {
            # GRP archives (different from NE)
        },
        'audio_files': {
            'sounds_main': 'SSBWINCD/SSBSOUND.DLL',
            'sounds_2': 'SSBWINCD/SS2SOUND.DLL',
            'sounds_3': 'SSBWINCD/SS3SOUND.DLL',
            'sounds_f': 'SSBWINCD/SSFSOUND.DLL',
        },
        'grp_files': {
            'ws107a': 'ASSETS/WS107A.GRP',
            'ws109': 'ASSETS/WS109.GRP',
            'ws203': 'ASSETS/WS203.GRP',
            'wscommon': 'ASSETS/WSCOMMON.GRP',
            'ws107ap': 'ASSETS/WS107AP.GRP',
            'ws109p': 'ASSETS/WS109P.GRP',
        },
        'midi_dir': None,
        'game_data': {
            'main': 'SSBWINCD/SSB.DLL',
            'wordlist': 'SSBWINCD/WORDLIST.DAT',
        },
        'sprite_format': 'grp',
        'palette_source': 'grp',
        'video_dir': 'MOVIES',
    },
    'sbw': {
        'name': 'Storybook Weaver Deluxe',
        'company': 'MECC',
        'sprite_files': {
            # MECC proprietary archives
        },
        'audio_files': {},
        'mecc_archives': {
            'scenery': 'SCENERY.RES',
            'clipart': 'RESOURCE/ADN0001.ADN',
            'english': 'RESOURCE/ENG0001.ENG',
            'spanish': 'RESOURCE/SPN0001.SPN',
        },
        'wav_dir': 'TUNES',
        'midi_dir': 'TUNES',  # Mixed WAV and MIDI in same dir
        'music_index': 'RESOURCE/MUS0001.MUS',
        'sound_index': 'RESOURCE/SND0001.SND',
        'story_files': True,  # STARTR00-39.STS
        'game_data': {},
        'sprite_format': 'mecc',
        'palette_source': 'embedded',
        'video_dir': None,
    },
}


# ============================================================================
# Game Scanner - auto-detect games from file paths
# ============================================================================

def scan_for_games(base_path):
    """Scan a directory tree to find all game installations.

    Returns dict of game_id -> source_path.
    Each source_path is the directory that contains the game's relative paths.
    """
    found = {}
    base = Path(base_path)

    # Signature files for each game - these are relative to the game root
    signatures = {
        'ssg': ['SSGWINCD/GIZMO.DAT', 'SSGWINCD/GIZMO256.DAT'],
        'on':  ['ONWINCD/NEP256.DLL', 'ONWINCD/NEP.DLL'],
        'tmt': ['TMTWINCD/TMT256.DLL', 'TMTWINCD/TMT.DLL'],
        'tcv': ['TCVWINCD/TCV256.DLL', 'TCVWINCD/TCV.DLL'],
        'tms': ['DATA/TMSDATA.DAT', 'DATA/TMSSOUND.DAT'],
        'sso': ['SSOWINCD/SSO1.DAT', 'SSOWINCD/SND.DAT'],
        'ssr': ['SSRWINCD/SSR1.DAT', 'SSRWINCD/SFX.DAT'],
        'ssb': ['SSBWINCD/SSB.DLL', 'SSBWINCD/SSBSOUND.DLL'],
        'sbw': ['SCENERY.RES', 'RESOURCE/ADN0001.ADN'],
    }

    # Search in base_path and one level of subdirectories
    search_dirs = [base]
    try:
        search_dirs.extend([d for d in base.iterdir() if d.is_dir()])
    except PermissionError:
        pass

    # Also search two levels deep (e.g., base/mount_dir/GAME_DIR/)
    for d in list(search_dirs[1:]):
        try:
            search_dirs.extend([dd for dd in d.iterdir() if dd.is_dir()])
        except PermissionError:
            pass

    for search_dir in search_dirs:
        for game_id, sig_files in signatures.items():
            if game_id in found:
                continue
            for sig in sig_files:
                if (search_dir / sig).exists():
                    found[game_id] = str(search_dir)
                    break

    return found


# ============================================================================
# Sprite Extraction
# ============================================================================

def extract_rund_sprites(ne_path, palette, output_dir, label=""):
    """Extract RUND-format sprites from an NE file."""
    os.makedirs(output_dir, exist_ok=True)
    ne = NEResourceExtractor(ne_path)
    sprites_res = ne.list_by_type(CUSTOM_32513)
    count = 0

    for res in sprites_res:
        data = ne.extract(res)
        result = decompress_rund(data)
        if result is None:
            continue

        w, h, pixels = result
        fname = f"rund_{res.res_id}_{w}x{h}.bmp"
        write_bmp(os.path.join(output_dir, fname), w, h, pixels, palette)
        count += 1

    return count


def extract_rle_sprites(ne_path, palette, output_dir, label=""):
    """Extract RLE-compressed sprites from an NE file.

    Tries to find sprite dimensions from resource headers.
    """
    os.makedirs(output_dir, exist_ok=True)
    ne = NEResourceExtractor(ne_path)
    sprites_res = ne.list_by_type(CUSTOM_32513)
    count = 0

    for res in sprites_res:
        data = ne.extract(res)
        if len(data) < 16:
            continue

        # Try to detect format:
        # 1. Check for RUND magic at offset 4
        if len(data) >= 8 and data[4:8] == b'RUND':
            result = decompress_rund(data)
            if result:
                w, h, pixels = result
                fname = f"rund_{res.res_id}_{w}x{h}.bmp"
                write_bmp(os.path.join(output_dir, fname), w, h, pixels, palette)
                count += 1
                continue

        # 2. Try as sprite sheet with header: version(2) count(2) flags(10) offsets(4*count)
        version = struct.unpack('<H', data[0:2])[0]
        if version == 1 and len(data) > 14:
            sprite_count = struct.unpack('<H', data[2:4])[0]
            if 0 < sprite_count <= 500:
                # Read offset table
                header_size = 14  # version(2) + count(2) + reserved(10)
                offsets = []
                for i in range(sprite_count):
                    off_pos = header_size + i * 4
                    if off_pos + 4 <= len(data):
                        off = struct.unpack('<I', data[off_pos:off_pos+4])[0]
                        offsets.append(off)

                # Extract individual sprites using RLE
                for idx, off in enumerate(offsets):
                    if off >= len(data):
                        continue
                    # Determine end of this sprite's data
                    end = offsets[idx + 1] if idx + 1 < len(offsets) else len(data)
                    sprite_data = data[off:end]

                    # Try to estimate dimensions by counting 0x00 row terminators
                    rows = 0
                    max_row_width = 0
                    cur_width = 0
                    j = 0
                    while j < len(sprite_data):
                        if sprite_data[j] == 0x00:
                            rows += 1
                            max_row_width = max(max_row_width, cur_width)
                            cur_width = 0
                            j += 1
                        elif sprite_data[j] == 0xFF and j + 2 < len(sprite_data):
                            cur_width += sprite_data[j + 2]
                            j += 3
                        else:
                            cur_width += 1
                            j += 1

                    if rows > 0 and max_row_width > 0:
                        w = max_row_width
                        h = rows
                        pixels = decompress_rle_tlc(sprite_data, w * h)
                        fname = f"idx{res.res_id}_spr{idx:03d}_{w}x{h}.bmp"
                        write_bmp(os.path.join(output_dir, fname), w, h, pixels, palette)
                        count += 1
                continue

        # 3. Fallback: try as raw indexed pixels
        # Guess square-ish dimensions
        size = len(data)
        for test_w in [64, 48, 32, 80, 96, 128, 16]:
            if size >= test_w * 4:
                test_h = size // test_w
                if test_h > 0 and test_h < 1024:
                    fname = f"raw_{res.res_id}_{test_w}x{test_h}.bmp"
                    write_bmp(os.path.join(output_dir, fname), test_w, test_h,
                              data[:test_w * test_h], palette)
                    count += 1
                    break

    return count


def extract_sprites_for_game(game_id, source_path, output_dir, palette=None):
    """Extract sprites from a game, handling format differences."""
    game = GAME_DEFS[game_id]
    sprites_dir = os.path.join(output_dir, 'sprites')
    os.makedirs(sprites_dir, exist_ok=True)

    # Load palette
    if palette is None:
        palette = resolve_palette(game_id, source_path)

    total = 0
    fmt = game['sprite_format']

    for label, rel_path in game.get('sprite_files', {}).items():
        full_path = os.path.join(source_path, rel_path)
        if not os.path.exists(full_path):
            print(f"  [SKIP] {rel_path} not found")
            continue

        sub_dir = os.path.join(sprites_dir, label)
        print(f"  Extracting sprites: {rel_path} -> {label}/")

        try:
            ne = NEResourceExtractor(full_path)
        except (ValueError, struct.error) as e:
            print(f"  [ERROR] Not a valid NE file: {e}")
            continue

        if fmt == 'rund':
            count = extract_rund_sprites(full_path, palette, sub_dir, label)
        elif fmt == 'rle_tlc':
            count = extract_rle_sprites(full_path, palette, sub_dir, label)
        elif fmt == 'unknown':
            # Try both formats
            count = extract_rund_sprites(full_path, palette, sub_dir, label)
            if count == 0:
                count = extract_rle_sprites(full_path, palette, sub_dir, label)
        else:
            print(f"  [SKIP] Unsupported sprite format: {fmt}")
            count = 0

        total += count
        print(f"    -> {count} sprites extracted")

    # Handle GRP archives (SSB)
    for label, rel_path in game.get('grp_files', {}).items():
        full_path = os.path.join(source_path, rel_path)
        if not os.path.exists(full_path):
            print(f"  [SKIP] {rel_path} not found")
            continue

        sub_dir = os.path.join(sprites_dir, label)
        print(f"  Extracting GRP sprites: {rel_path} -> {label}/")

        count = extract_grp_sprites(full_path, palette, sub_dir, label)
        total += count
        print(f"    -> {count} sprites extracted")

    # Handle raw NE bitmap resources too
    for label, rel_path in game.get('sprite_files', {}).items():
        full_path = os.path.join(source_path, rel_path)
        if not os.path.exists(full_path):
            continue
        try:
            ne = NEResourceExtractor(full_path)
            bitmaps = ne.list_by_type(NE_RT_BITMAP)
            if bitmaps:
                bmp_dir = os.path.join(sprites_dir, f"{label}_bitmaps")
                os.makedirs(bmp_dir, exist_ok=True)
                for res in bitmaps:
                    data = ne.extract(res)
                    if len(data) > 40:
                        # Add BMP file header
                        header_size = struct.unpack('<I', data[0:4])[0]
                        bit_count = struct.unpack('<H', data[14:16])[0] if len(data) > 16 else 0
                        pal_size = 0
                        if bit_count <= 8:
                            color_count = struct.unpack('<I', data[32:36])[0] if len(data) > 36 else 0
                            if color_count == 0 and bit_count > 0:
                                color_count = 1 << bit_count
                            pal_size = color_count * 4
                        data_offset = 14 + header_size + pal_size
                        file_size = 14 + len(data)
                        file_header = b'BM' + struct.pack('<I', file_size) + b'\x00\x00\x00\x00' + struct.pack('<I', data_offset)
                        out_path = os.path.join(bmp_dir, f"bitmap_{res.res_id}.bmp")
                        with open(out_path, 'wb') as f:
                            f.write(file_header)
                            f.write(data)
                        total += 1
        except (ValueError, struct.error):
            pass

    return total


def resolve_palette(game_id, source_path):
    """Resolve the palette for a game."""
    game = GAME_DEFS[game_id]
    pal_src = game.get('palette_source', 'runtime')

    if pal_src.startswith('bmp:'):
        bmp_rel = pal_src[4:]
        bmp_path = os.path.join(source_path, bmp_rel)
        if os.path.exists(bmp_path):
            return load_palette_from_bmp(bmp_path)

    if pal_src == 'doubled':
        # Try to find doubled palette in CUSTOM_32515 resources
        for label, rel_path in game.get('game_data', {}).items():
            full_path = os.path.join(source_path, rel_path)
            if not os.path.exists(full_path):
                continue
            try:
                ne = NEResourceExtractor(full_path)
                for res in ne.list_by_type(CUSTOM_32515):
                    data = ne.extract(res)
                    if len(data) == 1536:
                        return load_doubled_palette(data)
                # Also check CUSTOM_32514
                for res in ne.list_by_type(CUSTOM_32514):
                    data = ne.extract(res)
                    if len(data) == 1536:
                        return load_doubled_palette(data)
            except (ValueError, struct.error):
                pass

    # Try loading from pre-extracted palette files
    palette_files = [
        os.path.join(os.path.dirname(source_path), f"{game_id}_palette.bin"),
        os.path.join(source_path, '..', f"{game_id}_palette.bin"),
    ]
    # Also check the ggng root for common palette files
    ggng_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    game_pal_names = {
        'ssg': 'gizmo_palette.bin',
        'on': 'neptune_palette.bin',
        'tmt': 'tmt_palette.bin',
        'tcv': 'tmt_palette.bin',  # Might share palette family
        'tms': 'tmt_palette.bin',
    }
    if game_id in game_pal_names:
        pal_path = os.path.join(ggng_root, game_pal_names[game_id])
        if os.path.exists(pal_path):
            try:
                return load_palette_from_raw(pal_path)
            except ValueError:
                pass

    print(f"  [WARN] No palette found for {game_id}, using grayscale")
    return grayscale_palette()


# ============================================================================
# Audio Extraction
# ============================================================================

def extract_audio_for_game(game_id, source_path, output_dir):
    """Extract all audio assets from a game."""
    game = GAME_DEFS[game_id]
    audio_dir = os.path.join(output_dir, 'audio')
    wav_dir = os.path.join(audio_dir, 'wav')
    midi_dir = os.path.join(audio_dir, 'midi')
    os.makedirs(wav_dir, exist_ok=True)
    os.makedirs(midi_dir, exist_ok=True)

    total_wav = 0
    total_midi = 0

    # 1. Extract WAV from NE resource files
    for label, rel_path in game.get('audio_files', {}).items():
        full_path = os.path.join(source_path, rel_path)
        if not os.path.exists(full_path):
            print(f"  [SKIP] {rel_path} not found")
            continue

        sub_dir = os.path.join(wav_dir, label)
        os.makedirs(sub_dir, exist_ok=True)
        print(f"  Extracting WAV: {rel_path} -> audio/wav/{label}/")

        try:
            ne = NEResourceExtractor(full_path)
            extracted = extract_wav_from_ne_all_types(ne, sub_dir)
            total_wav += len(extracted)
            print(f"    -> {len(extracted)} WAV files extracted")
        except (ValueError, struct.error) as e:
            print(f"  [ERROR] {e}")

    # 2. Copy standalone MIDI files
    midi_src = game.get('midi_dir')
    if midi_src:
        midi_src_path = os.path.join(source_path, midi_src)
        if os.path.isdir(midi_src_path):
            print(f"  Copying MIDI: {midi_src}/ -> audio/midi/")
            for fname in os.listdir(midi_src_path):
                src = os.path.join(midi_src_path, fname)
                if os.path.isfile(src) and fname.upper().endswith('.MID'):
                    dst = os.path.join(midi_dir, fname)
                    shutil.copy2(src, dst)
                    total_midi += 1
            print(f"    -> {total_midi} MIDI files copied")

    # 3. Copy standalone WAV files (SBW TUNES dir, TMS MUSIC dir)
    wav_src = game.get('wav_dir')
    if wav_src:
        wav_src_path = os.path.join(source_path, wav_src)
        if os.path.isdir(wav_src_path):
            standalone_dir = os.path.join(wav_dir, 'standalone')
            os.makedirs(standalone_dir, exist_ok=True)
            print(f"  Copying WAV: {wav_src}/ -> audio/wav/standalone/")
            wav_count = 0
            midi_extra = 0
            for fname in os.listdir(wav_src_path):
                src = os.path.join(wav_src_path, fname)
                if not os.path.isfile(src):
                    continue
                upper = fname.upper()
                if upper.endswith('.WAV'):
                    shutil.copy2(src, os.path.join(standalone_dir, fname))
                    wav_count += 1
                elif upper.endswith('.MID'):
                    shutil.copy2(src, os.path.join(midi_dir, fname))
                    midi_extra += 1
            total_wav += wav_count
            total_midi += midi_extra
            print(f"    -> {wav_count} WAV + {midi_extra} MIDI files copied")

    # 4. Extract WAV from sprite/game data files too (some games embed audio there)
    for label, rel_path in game.get('game_data', {}).items():
        full_path = os.path.join(source_path, rel_path)
        if not os.path.exists(full_path):
            continue
        # Don't re-extract from files already processed as audio
        if rel_path in [v for v in game.get('audio_files', {}).values()]:
            continue

        try:
            ne = NEResourceExtractor(full_path)
            # Check for WAV resources
            has_wav = False
            for res in ne.resources:
                data = ne.extract(res)
                if is_wav_data(data):
                    has_wav = True
                    break

            if has_wav:
                sub_dir = os.path.join(wav_dir, f"gamedata_{label}")
                os.makedirs(sub_dir, exist_ok=True)
                print(f"  Extracting embedded WAV: {rel_path} -> audio/wav/gamedata_{label}/")
                extracted = extract_wav_from_ne_all_types(ne, sub_dir)
                total_wav += len(extracted)
                print(f"    -> {len(extracted)} WAV files extracted")
        except (ValueError, struct.error):
            pass

    # 5. Extract WAVE audio from GRP archives
    for label, rel_path in game.get('grp_files', {}).items():
        full_path = os.path.join(source_path, rel_path)
        if not os.path.exists(full_path):
            continue

        sub_dir = os.path.join(wav_dir, f"grp_{label}")
        grp_count = extract_grp_audio(full_path, sub_dir)
        if grp_count > 0:
            total_wav += grp_count
            print(f"  Extracting GRP audio: {rel_path} -> audio/wav/grp_{label}/ ({grp_count} files)")

    return total_wav, total_midi


# ============================================================================
# Puzzle / Game Data Extraction
# ============================================================================

def extract_puzzles_for_game(game_id, source_path, output_dir):
    """Extract puzzle definitions, room data, and game logic resources."""
    game = GAME_DEFS[game_id]
    puzzle_dir = os.path.join(output_dir, 'puzzles')
    rooms_dir = os.path.join(output_dir, 'rooms')
    defs_dir = os.path.join(output_dir, 'definitions')
    raw_dir = os.path.join(output_dir, 'raw_resources')
    os.makedirs(puzzle_dir, exist_ok=True)
    os.makedirs(rooms_dir, exist_ok=True)
    os.makedirs(defs_dir, exist_ok=True)
    os.makedirs(raw_dir, exist_ok=True)

    total = 0

    for label, rel_path in game.get('game_data', {}).items():
        full_path = os.path.join(source_path, rel_path)
        if not os.path.exists(full_path):
            print(f"  [SKIP] {rel_path} not found")
            continue

        try:
            ne = NEResourceExtractor(full_path)
        except (ValueError, struct.error) as e:
            print(f"  [ERROR] Not a valid NE file: {rel_path}: {e}")
            continue

        print(f"  Analyzing: {rel_path} ({len(ne.resources)} resources)")

        # Extract CUSTOM_32515 - Game definitions
        defs = ne.list_by_type(CUSTOM_32515)
        if defs:
            sub_dir = os.path.join(defs_dir, label)
            os.makedirs(sub_dir, exist_ok=True)
            for res in defs:
                data = ne.extract(res)
                out_path = os.path.join(sub_dir, f"def_{res.res_id}.bin")
                with open(out_path, 'wb') as f:
                    f.write(data)
                total += 1

                # Try to identify puzzle type by resource ID range (SSG)
                if game_id == 'ssg':
                    puzzle_type = identify_ssg_puzzle_type(res.res_id)
                    if puzzle_type:
                        puz_dir = os.path.join(puzzle_dir, puzzle_type)
                        os.makedirs(puz_dir, exist_ok=True)
                        puz_path = os.path.join(puz_dir, f"def_{res.res_id}.bin")
                        with open(puz_path, 'wb') as f:
                            f.write(data)

            print(f"    -> {len(defs)} definition resources")

        # Extract CUSTOM_32516 - Room/level data
        rooms = ne.list_by_type(CUSTOM_32516)
        if rooms:
            sub_dir = os.path.join(rooms_dir, label)
            os.makedirs(sub_dir, exist_ok=True)
            for res in rooms:
                data = ne.extract(res)
                out_path = os.path.join(sub_dir, f"room_{res.res_id}.bin")
                with open(out_path, 'wb') as f:
                    f.write(data)
                total += 1

                # Analyze room header
                analyze_room(data, res.res_id, game_id, sub_dir)

            print(f"    -> {len(rooms)} room/level resources")

        # Extract CUSTOM_32517 / CUSTOM_32518 - Unknown (likely puzzle logic)
        for type_id, type_label in [(CUSTOM_32517, 'type_32517'), (CUSTOM_32518, 'type_32518')]:
            resources = ne.list_by_type(type_id)
            if resources:
                sub_dir = os.path.join(raw_dir, f"{label}_{type_label}")
                os.makedirs(sub_dir, exist_ok=True)
                for res in resources:
                    data = ne.extract(res)
                    out_path = os.path.join(sub_dir, f"res_{res.res_id}.bin")
                    with open(out_path, 'wb') as f:
                        f.write(data)
                    total += 1
                print(f"    -> {len(resources)} {type_label} resources")

        # Extract CUSTOM_15 - Header/animation/palette data
        customs = ne.list_by_type(CUSTOM_15)
        if customs:
            sub_dir = os.path.join(raw_dir, f"{label}_header")
            os.makedirs(sub_dir, exist_ok=True)
            for res in customs:
                data = ne.extract(res)
                out_path = os.path.join(sub_dir, f"header_{res.res_id}.bin")
                with open(out_path, 'wb') as f:
                    f.write(data)
                total += 1
            print(f"    -> {len(customs)} header/animation resources")

        # Extract all non-standard type resources (Operation Neptune uses 0x79xx range)
        non_standard = [r for r in ne.resources
                        if r.type_id not in (NE_RT_CURSOR, NE_RT_BITMAP, NE_RT_ICON,
                                             NE_RT_MENU, NE_RT_DIALOG, NE_RT_STRING,
                                             NE_RT_FONTDIR, NE_RT_FONT, NE_RT_ACCELERATOR,
                                             NE_RT_RCDATA, NE_RT_GROUP_CURSOR, NE_RT_GROUP_ICON,
                                             CUSTOM_15, CUSTOM_32513, CUSTOM_32514,
                                             CUSTOM_32515, CUSTOM_32516, CUSTOM_32517,
                                             CUSTOM_32518, CUSTOM_32519)]
        if non_standard:
            # Group by type
            types_seen = set()
            for res in non_standard:
                if res.type_id not in types_seen:
                    types_seen.add(res.type_id)
                    type_resources = [r for r in non_standard if r.type_id == res.type_id]
                    sub_dir = os.path.join(raw_dir, f"{label}_{type_name(res.type_id)}")
                    os.makedirs(sub_dir, exist_ok=True)
                    for r in type_resources:
                        data = ne.extract(r)
                        out_path = os.path.join(sub_dir, f"res_{r.res_id}.bin")
                        with open(out_path, 'wb') as f:
                            f.write(data)
                        total += 1
                    print(f"    -> {len(type_resources)} {type_name(res.type_id)} resources")

    # Handle Storybook Weaver stories
    if game_id == 'sbw':
        total += extract_sbw_stories(source_path, output_dir)

    return total


def identify_ssg_puzzle_type(res_id):
    """Identify SSG puzzle type from resource ID range."""
    ranges = {
        'balance': (42000, 43000),
        'electricity': (43000, 44000),
        'energy': (44000, 45000),
        'force': (45000, 46000),
        'gear': (46000, 47000),
        'jigsaw': (47000, 48000),
        'magnet': (48000, 49000),
        'simple_machine': (49000, 50000),
    }
    for ptype, (lo, hi) in ranges.items():
        if lo <= res_id < hi:
            return ptype
    return None


def analyze_room(data, res_id, game_id, output_dir):
    """Analyze and export room data as JSON."""
    if len(data) < 8:
        return

    info = {'res_id': res_id, 'size': len(data)}

    if game_id == 'ssg' and len(data) >= 8:
        building_id = struct.unpack('<H', data[0:2])[0]
        size_flags = struct.unpack('<H', data[2:4])[0]
        grid_w = struct.unpack('<H', data[4:6])[0]
        grid_h = struct.unpack('<H', data[6:8])[0]
        info.update({
            'building_id': building_id,
            'size_flags': size_flags,
            'grid_width': grid_w,
            'grid_height': grid_h,
        })

    json_path = os.path.join(output_dir, f"room_{res_id}.json")
    with open(json_path, 'w') as f:
        json.dump(info, f, indent=2)


def extract_sbw_stories(source_path, output_dir):
    """Extract Storybook Weaver story files (.STS)."""
    stories_dir = os.path.join(output_dir, 'stories')
    os.makedirs(stories_dir, exist_ok=True)

    count = 0
    for i in range(40):
        fname = f"STARTR{i:02d}.STS"
        src = os.path.join(source_path, fname)
        if os.path.exists(src):
            dst = os.path.join(stories_dir, fname)
            shutil.copy2(src, dst)

            # Parse story header
            with open(src, 'rb') as f:
                header = f.read(0x42)
                if len(header) >= 0x42:
                    ascii_header = header[:0x21].decode('ascii', errors='replace').rstrip('\x00')
                    f.seek(0x30)
                    page_count = struct.unpack('<I', f.read(4))[0]
                    f.seek(0x42)
                    title_bytes = f.read(64)
                    title = title_bytes.split(b'\x00')[0].decode('ascii', errors='replace')

                    info = {
                        'filename': fname,
                        'header': ascii_header,
                        'pages': page_count,
                        'title': title,
                    }
                    json_path = os.path.join(stories_dir, f"STARTR{i:02d}.json")
                    with open(json_path, 'w') as jf:
                        json.dump(info, jf, indent=2)

            count += 1

    # Copy story index
    lst_path = os.path.join(source_path, 'STRYSTRT.LST')
    if os.path.exists(lst_path):
        shutil.copy2(lst_path, os.path.join(stories_dir, 'STRYSTRT.LST'))

    if count:
        print(f"    -> {count} story files extracted")
    return count


# ============================================================================
# MECC Archive Extraction (Storybook Weaver)
# ============================================================================

def extract_mecc_resources(source_path, output_dir):
    """Extract what we can from MECC proprietary archives."""
    game = GAME_DEFS['sbw']
    mecc_dir = os.path.join(output_dir, 'mecc_archives')
    os.makedirs(mecc_dir, exist_ok=True)

    for label, rel_path in game.get('mecc_archives', {}).items():
        full_path = os.path.join(source_path, rel_path)
        if not os.path.exists(full_path):
            print(f"  [SKIP] {rel_path} not found")
            continue

        print(f"  Analyzing MECC archive: {rel_path}")
        sub_dir = os.path.join(mecc_dir, label)
        os.makedirs(sub_dir, exist_ok=True)

        with open(full_path, 'rb') as f:
            data = f.read(256)

        # Dump header for analysis
        header_path = os.path.join(sub_dir, f"{label}_header.bin")
        with open(header_path, 'wb') as f:
            f.write(data)

        # Try to identify format
        info = {'file': rel_path, 'size': os.path.getsize(full_path)}

        # Look for format tags
        for offset in range(len(data) - 8):
            chunk = data[offset:offset+8]
            if chunk == b'rsrcRSED':
                info['format'] = 'rsrcRSED'
                info['tag_offset'] = offset
                break
            elif chunk == b'RSRCDoug':
                info['format'] = 'RSRCDoug'
                info['tag_offset'] = offset
                break

        json_path = os.path.join(sub_dir, f"{label}_info.json")
        with open(json_path, 'w') as f:
            json.dump(info, f, indent=2)

        # Copy the UI bitmaps that are already standard format
        if label == 'scenery':
            bmp_dir = os.path.join(output_dir, 'sprites', 'ui_bitmaps')
            os.makedirs(bmp_dir, exist_ok=True)
            bmp_names = [
                'MAINMENU.BMP', 'MECC.BMP', 'SBWDLOGO.BMP', 'CHAIR.BMP',
                'TITLE1.BMP', 'TITLE2.BMP', 'DESK.BMP', 'PRINTER.BMP',
                'DOOR.BMP', 'TITLE3.BMP', 'MASTERPA.BMP', 'BLACK.BMP',
            ]
            copied = 0
            for bmp in bmp_names:
                bmp_src = os.path.join(source_path, bmp)
                if os.path.exists(bmp_src):
                    shutil.copy2(bmp_src, os.path.join(bmp_dir, bmp))
                    copied += 1
            if copied:
                print(f"    -> {copied} UI bitmaps copied")

    # Also try reading the music/sound index files
    for idx_file, idx_type in [('RESOURCE/MUS0001.MUS', 'music'), ('RESOURCE/SND0001.SND', 'sounds')]:
        idx_path = os.path.join(source_path, idx_file)
        if os.path.exists(idx_path):
            idx_out = os.path.join(mecc_dir, f"{idx_type}_index.txt")
            shutil.copy2(idx_path, idx_out)
            print(f"  Copied {idx_type} index: {idx_file}")


# ============================================================================
# Smacker Video Extraction
# ============================================================================

def extract_videos(game_id, source_path, output_dir):
    """Copy Smacker video files."""
    game = GAME_DEFS[game_id]
    video_src = game.get('video_dir')
    if not video_src:
        return 0

    video_src_path = os.path.join(source_path, video_src)
    if not os.path.isdir(video_src_path):
        return 0

    video_dir = os.path.join(output_dir, 'video')
    os.makedirs(video_dir, exist_ok=True)

    count = 0
    for fname in os.listdir(video_src_path):
        if fname.upper().endswith('.SMK'):
            src = os.path.join(video_src_path, fname)
            dst = os.path.join(video_dir, fname)
            shutil.copy2(src, dst)
            count += 1

    if count:
        print(f"  -> {count} Smacker video files copied")
    return count


# ============================================================================
# Main Extraction Pipeline
# ============================================================================

def extract_game(game_id, source_path, output_dir, extract_sprites=True,
                 extract_audio=True, extract_puzzles=True, extract_video=True):
    """Run full extraction pipeline for a single game."""
    game = GAME_DEFS[game_id]
    print(f"\n{'='*60}")
    print(f"  {game['name']} ({game_id.upper()})")
    print(f"  Company: {game['company']}")
    print(f"  Source: {source_path}")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}\n")

    os.makedirs(output_dir, exist_ok=True)
    manifest = {
        'game_id': game_id,
        'game_name': game['name'],
        'company': game['company'],
        'source_path': source_path,
        'sprites': 0,
        'wav_files': 0,
        'midi_files': 0,
        'puzzle_resources': 0,
        'video_files': 0,
    }

    if extract_sprites:
        print("[SPRITES]")
        if game_id == 'sbw':
            extract_mecc_resources(source_path, output_dir)
        else:
            manifest['sprites'] = extract_sprites_for_game(game_id, source_path, output_dir)
        print()

    if extract_audio:
        print("[AUDIO]")
        wav, midi = extract_audio_for_game(game_id, source_path, output_dir)
        manifest['wav_files'] = wav
        manifest['midi_files'] = midi
        print()

    if extract_puzzles:
        print("[PUZZLES & GAME DATA]")
        manifest['puzzle_resources'] = extract_puzzles_for_game(game_id, source_path, output_dir)
        print()

    if extract_video:
        print("[VIDEO]")
        manifest['video_files'] = extract_videos(game_id, source_path, output_dir)
        print()

    # Write manifest
    manifest_path = os.path.join(output_dir, 'manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"Summary for {game['name']}:")
    print(f"  Sprites:    {manifest['sprites']}")
    print(f"  WAV files:  {manifest['wav_files']}")
    print(f"  MIDI files: {manifest['midi_files']}")
    print(f"  Puzzle/data:{manifest['puzzle_resources']}")
    print(f"  Videos:     {manifest['video_files']}")
    print(f"  Manifest:   {manifest_path}")

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description='OpenGizmos Unified Asset Extractor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Games:
  ssg  - Super Solvers: Gizmos & Gadgets
  on   - Operation Neptune
  tmt  - Treasure Mountain!
  tcv  - Treasure Cove!
  tms  - Treasure MathStorm!
  sso  - Super Solvers: OutNumbered!
  ssr  - Super Solvers: Spellbound!
  ssb  - Super Solvers: Spellbound Wizards
  sbw  - Storybook Weaver Deluxe (MECC)

Examples:
  %(prog)s scan C:\\ggng
  %(prog)s on C:\\ggng\\ONWINCD C:\\ggng\\extracted\\on --all
  %(prog)s all C:\\ggng C:\\ggng\\extracted
  %(prog)s ssg C:\\ggng\\iso C:\\ggng\\extracted\\ssg --sprites --audio
""")

    parser.add_argument('game', help='Game ID, "scan", or "all"')
    parser.add_argument('source', help='Source directory (game root or base path)')
    parser.add_argument('output', nargs='?', default=None, help='Output directory')
    parser.add_argument('--sprites', action='store_true', help='Extract sprites')
    parser.add_argument('--audio', action='store_true', help='Extract audio')
    parser.add_argument('--puzzles', action='store_true', help='Extract puzzle/game data')
    parser.add_argument('--video', action='store_true', help='Extract video files')
    parser.add_argument('--all', action='store_true', help='Extract everything')
    parser.add_argument('--palette', help='Override palette file path')

    args = parser.parse_args()

    # Determine what to extract
    if args.all or not any([args.sprites, args.audio, args.puzzles, args.video]):
        do_sprites = do_audio = do_puzzles = do_video = True
    else:
        do_sprites = args.sprites
        do_audio = args.audio
        do_puzzles = args.puzzles
        do_video = args.video

    if args.game == 'scan':
        print("Scanning for games...\n")
        found = scan_for_games(args.source)
        if not found:
            print("No games found!")
            return 1
        for gid, path in sorted(found.items()):
            game = GAME_DEFS[gid]
            print(f"  {gid.upper():4s} - {game['name']}")
            print(f"         {path}")
        print(f"\nFound {len(found)} games.")
        return 0

    if args.game == 'all':
        if not args.output:
            print("Error: output directory required for 'all' mode")
            return 1

        print("Scanning for all games...\n")
        found = scan_for_games(args.source)
        if not found:
            print("No games found!")
            return 1

        print(f"Found {len(found)} games. Extracting all...\n")
        all_manifests = {}
        for gid, path in sorted(found.items()):
            game_out = os.path.join(args.output, gid)
            manifest = extract_game(gid, path, game_out,
                                    do_sprites, do_audio, do_puzzles, do_video)
            all_manifests[gid] = manifest

        # Write combined manifest
        combined_path = os.path.join(args.output, 'all_games_manifest.json')
        with open(combined_path, 'w') as f:
            json.dump(all_manifests, f, indent=2)

        print(f"\n{'='*60}")
        print("  EXTRACTION COMPLETE")
        print(f"{'='*60}")
        total_sprites = sum(m['sprites'] for m in all_manifests.values())
        total_wav = sum(m['wav_files'] for m in all_manifests.values())
        total_midi = sum(m['midi_files'] for m in all_manifests.values())
        total_puzzle = sum(m['puzzle_resources'] for m in all_manifests.values())
        total_video = sum(m['video_files'] for m in all_manifests.values())
        print(f"  Games:     {len(all_manifests)}")
        print(f"  Sprites:   {total_sprites}")
        print(f"  WAV files: {total_wav}")
        print(f"  MIDI:      {total_midi}")
        print(f"  Puzzles:   {total_puzzle}")
        print(f"  Videos:    {total_video}")
        print(f"  Manifest:  {combined_path}")
        return 0

    # Single game extraction
    if args.game not in GAME_DEFS:
        print(f"Unknown game: {args.game}")
        print(f"Valid games: {', '.join(sorted(GAME_DEFS.keys()))}")
        return 1

    if not args.output:
        args.output = os.path.join(args.source, '..', 'extracted', args.game)

    extract_game(args.game, args.source, args.output,
                 do_sprites, do_audio, do_puzzles, do_video)
    return 0


if __name__ == '__main__':
    sys.exit(main())
