r"""
❤Music — Binary Signature Analyzer for Released Audio

Scans audio files (WAV, MP3, FLAC, AIFF), extracts binary forensics
(hashes, entropy, codec info, provenance), and saves to the
release_signatures table in heartmusic.db.

Pipeline: Pro Tools (Hyperthreat Studios) → Suno → distribution

Usage:
    # Analyze a single file
    C:\G\python.exe src/analysis/sig_analyzer.py "C:\Users\tyler\Desktop\Marigolds.wav"

    # Analyze with explicit track/recording linkage
    C:\G\python.exe src/analysis/sig_analyzer.py "C:\Users\tyler\Desktop\Marigolds.mp3" --track-id 13

    # Analyze a directory of release files
    C:\G\python.exe src/analysis/sig_analyzer.py "C:\Users\tyler\Desktop" --track-id 13

    # Dry-run (print analysis, don't save)
    C:\G\python.exe src/analysis/sig_analyzer.py "C:\path\to\file.wav" --dry-run

    # Re-analyze (update existing signature by sha256)
    C:\G\python.exe src/analysis/sig_analyzer.py "C:\path\to\file.wav" --force
"""

import argparse
import hashlib
import json
import math
import os
import re
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # ❤Music/
sys.path.insert(0, str(PROJECT_ROOT / "src"))
# Add executedcode/ for quantum_rt shim
sys.path.insert(0, str(PROJECT_ROOT.parent))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT.parent / ".env")

from utils.init_db import get_connection

AUDIO_EXTS = {".wav", ".mp3", ".flac", ".aiff", ".aif"}
QUANTUM_SALT_BITS = 256
SIG_VERSION = "2.0.0"  # Full TJD signature suite


def _md5_fingerprint(data: bytes) -> str:
    """Compatibility fingerprint only; not used for security decisions."""
    try:
        digest = hashlib.new("md5", data, usedforsecurity=False)
    except TypeError:
        digest = hashlib.new("md5", data)
    return digest.hexdigest()


def compute_hashes(data: bytes) -> dict[str, str]:
    """Full deterministic hash suite."""
    return {
        "md5": _md5_fingerprint(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "blake2s": hashlib.blake2s(data).hexdigest(),
        "sha512": hashlib.sha512(data).hexdigest(),
        "sha512_224": hashlib.new("sha512_224", data).hexdigest(),
        "sha512_256": hashlib.new("sha512_256", data).hexdigest(),
        "shake_128": hashlib.shake_128(data).hexdigest(32),    # 256-bit output
        "shake_256": hashlib.shake_256(data).hexdigest(64),    # 512-bit output
        "whirlpool": hashlib.new("whirlpool", data).hexdigest(),
    }


def compute_quantum_hashes(data: bytes, deterministic_hashes: dict[str, str]) -> dict[str, Any]:
    """Quantum-enhanced: keyed BLAKE2b + SHA3-512 + ChaCha20-Poly1305 + AES-256-GCM seals."""
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305, AESGCM

    # --- Quantum salt ---
    try:
        from quantum_rt import qRandomBitstring, bitstring_cache
        cache_len = len(bitstring_cache) if bitstring_cache else 0
        has_quantum = cache_len >= QUANTUM_SALT_BITS
        salt_bits = qRandomBitstring(QUANTUM_SALT_BITS)
        source = "ibm_quantum_cache" if has_quantum else "classical_fallback"
    except ImportError:
        import random
        salt_bits = "".join(random.choice("01") for _ in range(QUANTUM_SALT_BITS))
        source = "classical_fallback"

    salt_bytes = int(salt_bits, 2).to_bytes(QUANTUM_SALT_BITS // 8, byteorder="big")
    salt_hex = salt_bytes.hex()

    # --- Keyed BLAKE2b + SHA3-512 ---
    blake2b_sig = hashlib.blake2b(data, key=salt_bytes, digest_size=64).hexdigest()
    sha3_sig = hashlib.sha3_512(data).hexdigest()

    # --- AEAD seals: sign the SHA-256 digest with quantum-derived keys ---
    # The plaintext being sealed is the sha256 — proving key holder authenticated this file
    plaintext = deterministic_hashes["sha256"].encode("utf-8")
    aad = f"{deterministic_hashes['sha256']}".encode("utf-8")

    # 12-byte nonce from quantum salt (first 12 bytes)
    nonce = salt_bytes[:12]

    # ChaCha20-Poly1305 seal (key = first 32 bytes of quantum salt)
    chacha_key = salt_bytes[:32]
    chacha = ChaCha20Poly1305(chacha_key)
    chacha_seal = chacha.encrypt(nonce, plaintext, aad).hex()

    # AES-256-GCM seal (key = BLAKE2s of quantum salt, 32 bytes)
    aes_key = hashlib.blake2s(salt_bytes, digest_size=32).digest()
    aesgcm = AESGCM(aes_key)
    aesgcm_seal = aesgcm.encrypt(nonce, plaintext, aad).hex()

    return {
        "quantum_salt": salt_hex,
        "quantum_blake2b": blake2b_sig,
        "quantum_sha3_512": sha3_sig,
        "quantum_entropy_bits": QUANTUM_SALT_BITS,
        "quantum_source": source,
        "quantum_signed_at": datetime.now(timezone.utc).isoformat(),
        "chacha20_poly1305_seal": chacha_seal,
        "aesgcm_seal": aesgcm_seal,
        "aead_nonce": nonce.hex(),
        "aead_aad": aad.decode("utf-8"),
        "sig_version": SIG_VERSION,
    }


def byte_entropy(block: bytes) -> float:
    if not block:
        return 0.0
    freq = [0] * 256
    for b in block:
        freq[b] += 1
    n = len(block)
    return -sum((c / n) * math.log2(c / n) for c in freq if c > 0)


def byte_freq_top10(block: bytes) -> list[dict[str, Any]]:
    freq = [0] * 256
    for b in block:
        freq[b] += 1
    total = sum(freq)
    ranked = sorted(enumerate(freq), key=lambda x: -x[1])
    return [
        {"byte": f"0x{val:02x}", "count": count, "pct": round(count / total * 100, 2)}
        for val, count in ranked[:10]
    ]


def boundary_crossings(block: bytes) -> tuple[int, float]:
    if len(block) < 2:
        return 0, 0.0
    cx = sum(1 for i in range(1, len(block)) if (block[i - 1] < 128) != (block[i] < 128))
    rate = cx / len(block) * 100
    return cx, round(rate, 2)


def parse_mp3(data: bytes) -> dict[str, Any]:
    info: dict[str, Any] = {
        "container": "MPEG",
        "codec": None,
        "sample_rate_hz": None,
        "channels": None,
        "bits_per_sample": None,
        "bitrate_kbps": None,
        "duration_sec": None,
        "provenance_url": None,
        "provenance_comment": None,
        "created_timestamp": None,
        "provenance_id": None,
    }

    audio_offset = 0

    # ID3v2 tag
    if data[:3] == b"ID3":
        v_maj, v_min, flags = data[3], data[4], data[5]
        tag_size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
        audio_offset = tag_size + 10
        info["_id3v2"] = f"ID3v2.{v_maj}.{v_min}"

        # Parse ID3v2 frames for provenance
        pos = 10
        while pos < audio_offset - 10:
            frame_id = data[pos:pos + 4].decode("ascii", "replace")
            if frame_id[0] == "\x00":
                break
            frame_size = struct.unpack_from(">I", data, pos + 4)[0]
            frame_data = data[pos + 10:pos + 10 + frame_size]

            if frame_id == "WOAS":  # Official audio source URL
                url = frame_data.decode("latin-1", "replace").strip("\x00")
                info["provenance_url"] = url
                # Extract Suno ID from URL
                m = re.search(r"suno\.com/song/([a-f0-9\-]+)", url)
                if m:
                    info["provenance_id"] = m.group(1)
                    info["source_platform"] = "suno"
            elif frame_id == "COMM":  # Comment
                # Skip encoding byte + language + short desc
                try:
                    comment = frame_data.split(b"\x00")[-1].decode("utf-8", "replace")
                    info["provenance_comment"] = comment
                except Exception:
                    pass
            elif frame_id == "TDRC":  # Recording date
                try:
                    info["created_timestamp"] = frame_data[1:].decode("utf-8", "replace").strip("\x00")
                except Exception:
                    pass

            pos += 10 + frame_size

    # First MPEG frame
    if audio_offset < len(data) - 4:
        fh = data[audio_offset:audio_offset + 4]
        if fh[0] == 0xFF and (fh[1] & 0xE0) == 0xE0:
            vb = (fh[1] >> 3) & 3
            lb = (fh[1] >> 1) & 3
            br_i = (fh[2] >> 4) & 0xF
            sr_i = (fh[2] >> 2) & 3
            ch = (fh[3] >> 6) & 3

            vers_map = {0: "2.5", 2: "2", 3: "1"}
            layer_map = {1: "III", 2: "II", 3: "I"}
            br_table = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
            sr_table = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}
            ch_map = {0: 2, 1: 2, 2: 2, 3: 1}

            ver = vers_map.get(vb, "?")
            layer = layer_map.get(lb, "?")
            info["codec"] = f"MPEG{ver}-Layer{layer}"

            if vb in sr_table and sr_i < 3:
                info["sample_rate_hz"] = sr_table[vb][sr_i]
            info["channels"] = ch_map.get(ch, 2)

            # Average bitrate from file size and estimated duration
            audio_bytes = len(data) - audio_offset
            first_br = br_table[br_i] if vb == 3 and lb == 1 else 0
            if first_br > 0 and info["sample_rate_hz"]:
                # For VBR, estimate from file size; for CBR use frame bitrate
                # Better estimate: assume VBR, use file-size method
                info["bitrate_kbps"] = round(audio_bytes * 8 / 1000 / (audio_bytes * 8 / (first_br * 1000)), 1)
                # More accurate: calculate from file size if we can find duration elsewhere
                # For now, use file-level average
                avg_br = audio_bytes * 8 / 1000  # total kbits
                est_dur = avg_br / first_br  # seconds (rough for VBR)
                info["duration_sec"] = round(est_dur, 1)
                info["bitrate_kbps"] = round(audio_bytes * 8 / (est_dur * 1000), 1) if est_dur > 0 else first_br

    # ID3v1 at end
    if data[-128:-125] == b"TAG":
        info["_id3v1_title"] = data[-125:-95].decode("latin-1", "replace").strip("\x00").strip()

    return info


def parse_wav(data: bytes) -> dict[str, Any]:
    info: dict[str, Any] = {
        "container": "RIFF/WAVE",
        "codec": None,
        "sample_rate_hz": None,
        "channels": None,
        "bits_per_sample": None,
        "bitrate_kbps": None,
        "duration_sec": None,
        "provenance_url": None,
        "provenance_comment": None,
        "created_timestamp": None,
        "provenance_id": None,
    }

    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return info

    riff_size = struct.unpack_from("<I", data, 4)[0]
    off = 12
    data_chunk_size = 0

    while off < min(len(data) - 8, 65536):
        cid = data[off:off + 4].decode("ascii", "replace")
        csz = struct.unpack_from("<I", data, off + 4)[0]

        if cid == "fmt ":
            fd = data[off + 8:off + 8 + csz]
            af = struct.unpack_from("<H", fd, 0)[0]
            fmt_names = {1: "PCM", 3: "IEEE_Float", 6: "A-law", 7: "mu-law", 0xFFFE: "Extensible"}
            info["codec"] = fmt_names.get(af, f"fmt_{af}")
            info["channels"] = struct.unpack_from("<H", fd, 2)[0]
            info["sample_rate_hz"] = struct.unpack_from("<I", fd, 4)[0]
            byte_rate = struct.unpack_from("<I", fd, 8)[0]
            info["bits_per_sample"] = struct.unpack_from("<H", fd, 14)[0]
            info["bitrate_kbps"] = round(byte_rate * 8 / 1000, 1)

        elif cid == "data":
            data_chunk_size = csz

        elif cid == "LIST":
            # Parse INFO sub-chunks for provenance
            list_type = data[off + 8:off + 12].decode("ascii", "replace")
            if list_type == "INFO":
                ioff = off + 12
                while ioff < off + 8 + csz:
                    sub_id = data[ioff:ioff + 4].decode("ascii", "replace")
                    sub_sz = struct.unpack_from("<I", data, ioff + 4)[0]
                    sub_data = data[ioff + 8:ioff + 8 + sub_sz].decode("utf-8", "replace").strip("\x00")
                    if sub_id == "ICMT":
                        info["provenance_comment"] = sub_data
                        # Parse Suno metadata from ICMT
                        m = re.search(r"id=([a-f0-9\-]+)", sub_data)
                        if m:
                            info["provenance_id"] = m.group(1)
                        if "suno" in sub_data.lower():
                            info["source_platform"] = "suno"
                        m2 = re.search(r"created=(\S+)", sub_data)
                        if m2:
                            info["created_timestamp"] = m2.group(1)
                    ioff += 8 + sub_sz
                    if sub_sz % 2:
                        ioff += 1

        off += 8 + csz
        if csz % 2:
            off += 1

    # Duration from data chunk + byte rate
    if data_chunk_size and info.get("bitrate_kbps"):
        byte_rate = info["bitrate_kbps"] * 1000 / 8
        info["duration_sec"] = round(data_chunk_size / byte_rate, 1) if byte_rate else None
    elif info.get("bitrate_kbps"):
        byte_rate = info["bitrate_kbps"] * 1000 / 8
        info["duration_sec"] = round(riff_size / byte_rate, 1) if byte_rate else None

    return info


def analyze_file(file_path: str, quantum: bool = True) -> dict[str, Any]:
    """Full binary signature analysis of an audio file."""
    p = Path(file_path)
    with open(p, "rb") as f:
        data = f.read()

    size = len(data)
    ext = p.suffix.lower()
    hashes = compute_hashes(data)

    # Entropy
    header_block = data[:65536]
    mid_start = size // 2
    mid_block = data[mid_start:mid_start + 65536]

    ent_header = round(byte_entropy(header_block), 4)
    ent_mid = round(byte_entropy(mid_block), 4)
    top10 = byte_freq_top10(header_block)
    cx, cx_rate = boundary_crossings(header_block)

    # Format-specific parsing
    if ext == ".mp3":
        fmt_info = parse_mp3(data)
    elif ext in (".wav",):
        fmt_info = parse_wav(data)
    else:
        fmt_info = {"container": ext.lstrip(".").upper(), "codec": None}

    result = {
        "file_path": str(p.resolve()),
        "file_size_bytes": size,
        "file_format": ext.lstrip("."),
        "md5": hashes["md5"],
        "sha256": hashes["sha256"],
        "blake2s": hashes["blake2s"],
        "sha512": hashes["sha512"],
        "sha512_224": hashes["sha512_224"],
        "sha512_256": hashes["sha512_256"],
        "shake_128": hashes["shake_128"],
        "shake_256": hashes["shake_256"],
        "whirlpool": hashes["whirlpool"],
        "container": fmt_info.get("container"),
        "codec": fmt_info.get("codec"),
        "sample_rate_hz": fmt_info.get("sample_rate_hz"),
        "channels": fmt_info.get("channels"),
        "bits_per_sample": fmt_info.get("bits_per_sample"),
        "bitrate_kbps": fmt_info.get("bitrate_kbps"),
        "duration_sec": fmt_info.get("duration_sec"),
        "entropy_header": ent_header,
        "entropy_mid": ent_mid,
        "boundary_crossings": cx,
        "crossing_rate_pct": cx_rate,
        "byte_freq_top10": json.dumps(top10),
        "source_platform": fmt_info.get("source_platform"),
        "provenance_id": fmt_info.get("provenance_id"),
        "provenance_url": fmt_info.get("provenance_url"),
        "created_timestamp": fmt_info.get("created_timestamp"),
        "provenance_comment": fmt_info.get("provenance_comment"),
    }

    if quantum:
        result.update(compute_quantum_hashes(data, hashes))
    else:
        result.update({
            "quantum_salt": None, "quantum_blake2b": None,
            "quantum_sha3_512": None, "quantum_entropy_bits": None,
            "quantum_source": None, "quantum_signed_at": None,
            "chacha20_poly1305_seal": None, "aesgcm_seal": None,
            "aead_nonce": None, "aead_aad": None,
            "sig_version": SIG_VERSION,
        })

    return result


def save_signature(
    sig: dict[str, Any],
    track_id: int | None = None,
    recording_id: int | None = None,
    pipeline: str | None = None,
    pipeline_notes: str | None = None,
    force: bool = False,
) -> int:
    """Insert signature into release_signatures table. Returns row id."""
    conn = get_connection()
    try:
        # Check for existing by sha256
        existing = conn.execute(
            "SELECT id FROM release_signatures WHERE sha256 = ?",
            (sig["sha256"],),
        ).fetchone()

        if existing and not force:
            row_id = existing[0] if isinstance(existing, tuple) else existing["id"]
            print(f"  Signature already exists (id={row_id}). Use --force to update.")
            return row_id

        if existing and force:
            row_id = existing[0] if isinstance(existing, tuple) else existing["id"]
            conn.execute("DELETE FROM release_signatures WHERE id = ?", (row_id,))

        cur = conn.execute(
            """INSERT INTO release_signatures (
                recording_id, track_id, file_path, file_size_bytes, file_format,
                md5, sha256, container, codec, sample_rate_hz, channels,
                bits_per_sample, bitrate_kbps, duration_sec,
                entropy_header, entropy_mid, boundary_crossings, crossing_rate_pct,
                byte_freq_top10, source_platform, provenance_id, provenance_url,
                created_timestamp, provenance_comment, pipeline, pipeline_notes,
                blake2s, sha512, sha512_224, sha512_256, shake_128, shake_256, whirlpool,
                quantum_salt, quantum_blake2b, quantum_sha3_512,
                quantum_entropy_bits, quantum_source, quantum_signed_at,
                chacha20_poly1305_seal, aesgcm_seal, aead_nonce, aead_aad, sig_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                recording_id, track_id, sig["file_path"], sig["file_size_bytes"],
                sig["file_format"], sig["md5"], sig["sha256"],
                sig["container"], sig["codec"], sig["sample_rate_hz"],
                sig["channels"], sig["bits_per_sample"], sig["bitrate_kbps"],
                sig["duration_sec"], sig["entropy_header"], sig["entropy_mid"],
                sig["boundary_crossings"], sig["crossing_rate_pct"],
                sig["byte_freq_top10"], sig["source_platform"],
                sig["provenance_id"], sig["provenance_url"],
                sig["created_timestamp"], sig["provenance_comment"],
                pipeline, pipeline_notes,
                sig.get("blake2s"), sig.get("sha512"),
                sig.get("sha512_224"), sig.get("sha512_256"),
                sig.get("shake_128"), sig.get("shake_256"), sig.get("whirlpool"),
                sig.get("quantum_salt"), sig.get("quantum_blake2b"),
                sig.get("quantum_sha3_512"), sig.get("quantum_entropy_bits"),
                sig.get("quantum_source"), sig.get("quantum_signed_at"),
                sig.get("chacha20_poly1305_seal"), sig.get("aesgcm_seal"),
                sig.get("aead_nonce"), sig.get("aead_aad"), sig.get("sig_version"),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def print_analysis(sig: dict[str, Any]) -> None:
    """Pretty-print the analysis to console."""
    print(f"\n  File:       {sig['file_path']}")
    print(f"  Size:       {sig['file_size_bytes']:,} bytes ({sig['file_size_bytes']/1024/1024:.2f} MB)")
    print(f"  Format:     {sig['file_format']} / {sig['container']} / {sig['codec']}")
    print(f"  ── Deterministic Hashes ─────────────────")
    print(f"  MD5:        {sig['md5']}")
    print(f"  SHA-256:    {sig['sha256']}")
    print(f"  BLAKE2s:    {sig.get('blake2s', 'N/A')}")
    print(f"  SHA-512:    {sig.get('sha512', 'N/A')[:64]}...")
    print(f"  SHA-512/224:{sig.get('sha512_224', 'N/A')}")
    print(f"  SHA-512/256:{sig.get('sha512_256', 'N/A')}")
    print(f"  SHAKE-128:  {sig.get('shake_128', 'N/A')}")
    print(f"  SHAKE-256:  {sig.get('shake_256', 'N/A')[:64]}...")
    print(f"  Whirlpool:  {sig.get('whirlpool', 'N/A')[:64]}...")
    print(f"  ── Audio ────────────────────────────────")
    print(f"  Sample rate:{sig['sample_rate_hz']} Hz  Channels: {sig['channels']}  Bits: {sig['bits_per_sample']}")
    print(f"  Bitrate:    {sig['bitrate_kbps']} kbps")
    dur = sig.get("duration_sec")
    if dur:
        print(f"  Duration:   {dur:.1f}s ({int(dur // 60)}m {dur % 60:.1f}s)")
    print(f"  Entropy:    header={sig['entropy_header']}  mid={sig['entropy_mid']}  (max=8.0)")
    print(f"  Crossings:  {sig['boundary_crossings']:,}  rate={sig['crossing_rate_pct']}%")
    if sig.get("source_platform"):
        print(f"  Platform:   {sig['source_platform']}")
    if sig.get("provenance_id"):
        print(f"  Prov ID:    {sig['provenance_id']}")
    if sig.get("provenance_url"):
        print(f"  Prov URL:   {sig['provenance_url']}")
    if sig.get("created_timestamp"):
        print(f"  Created:    {sig['created_timestamp']}")
    if sig.get("provenance_comment"):
        print(f"  Comment:    {sig['provenance_comment'][:120]}")
    top10 = json.loads(sig["byte_freq_top10"])
    top_str = ", ".join(f"{b['byte']}={b['pct']}%" for b in top10[:5])
    print(f"  Top bytes:  {top_str}")
    # Quantum + AEAD signature
    if sig.get("quantum_salt"):
        print(f"  ── Quantum + AEAD ───────────────────────")
        print(f"  Q-Salt:     {sig['quantum_salt']}")
        print(f"  BLAKE2b:    {sig['quantum_blake2b']}")
        print(f"  SHA3-512:   {sig['quantum_sha3_512']}")
        print(f"  ChaCha20:   {sig.get('chacha20_poly1305_seal', 'N/A')}")
        print(f"  AES-GCM:    {sig.get('aesgcm_seal', 'N/A')}")
        print(f"  Nonce:      {sig.get('aead_nonce', 'N/A')}")
        print(f"  Q-Source:   {sig['quantum_source']}  ({sig['quantum_entropy_bits']} bits)")
        print(f"  Q-Signed:   {sig['quantum_signed_at']}")
        print(f"  Version:    {sig.get('sig_version', '1.0.0')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="❤Music Binary Signature Analyzer — scan audio files, extract forensics, save to DB"
    )
    parser.add_argument("path", help="Audio file or directory to analyze")
    parser.add_argument("--track-id", type=int, help="Link to tracks(id)")
    parser.add_argument("--recording-id", type=int, help="Link to recordings(id)")
    parser.add_argument("--pipeline", default="pro_tools→suno", help="Pipeline label (default: pro_tools→suno)")
    parser.add_argument("--pipeline-notes", help="Extra pipeline context")
    parser.add_argument("--dry-run", action="store_true", help="Analyze and print but don't save")
    parser.add_argument("--force", action="store_true", help="Overwrite existing signature (by sha256)")
    parser.add_argument("--no-quantum", action="store_true", help="Skip quantum-enhanced hashing")
    args = parser.parse_args()

    target = Path(args.path)
    if target.is_dir():
        files = sorted(f for f in target.iterdir() if f.suffix.lower() in AUDIO_EXTS)
    elif target.is_file() and target.suffix.lower() in AUDIO_EXTS:
        files = [target]
    else:
        print(f"Error: {target} is not a valid audio file or directory.")
        sys.exit(1)

    if not files:
        print("No audio files found.")
        sys.exit(1)

    print(f"Analyzing {len(files)} file(s)...")
    for f in files:
        print(f"\n{'─' * 60}")
        print(f"  Scanning: {f.name}")
        sig = analyze_file(str(f), quantum=not args.no_quantum)
        print_analysis(sig)

        if not args.dry_run:
            row_id = save_signature(
                sig,
                track_id=args.track_id,
                recording_id=args.recording_id,
                pipeline=args.pipeline,
                pipeline_notes=args.pipeline_notes,
                force=args.force,
            )
            print(f"  → Saved to release_signatures (id={row_id})")
        else:
            print("  → [dry-run] Not saved.")

    print(f"\n{'─' * 60}")
    print(f"Done. {len(files)} file(s) analyzed.")


if __name__ == "__main__":
    main()
