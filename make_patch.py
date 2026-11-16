#!/usr/bin/env python3
"""Build a CDP1 patch from a pristine ISO and a finished review ISO.

This is the maintainer-side counterpart to culdcept_patch.py.  It is not needed
to apply a released patch.  Both images are read in bounded chunks, so the
builder does not load a multi-gigabyte ISO into memory.

The output contains only changed byte ranges, compressed independently with
zlib.  Adjacent differences separated by at most --merge-gap unchanged bytes
are kept in one range; this avoids thousands of tiny ranges in code areas while
keeping large unchanged stretches out of the patch.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zlib
from pathlib import Path

MAGIC = b"CDP1"
FORMAT_VERSION = 1
HEADER = struct.Struct("<4sHHQQ32s32sI")
SEGMENT_HEADER = struct.Struct("<QQI")
CHUNK = 8 * 1024 * 1024
DEFAULT_MERGE_GAP = 64


def hash_file(path: Path) -> bytes:
    """Hash a complete image without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        while True:
            chunk = handle.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.digest()


def scan_ranges(source: Path, target: Path, merge_gap: int) -> list[tuple[int, int]]:
    """Return merged (start, end) ranges over the common prefix and target tail."""
    source_size = source.stat().st_size
    target_size = target.stat().st_size
    common_size = min(source_size, target_size)
    ranges: list[tuple[int, int]] = []
    position = 0

    with source.open("rb", buffering=0) as src, target.open("rb", buffering=0) as tgt:
        while position < common_size:
            count = min(CHUNK, common_size - position)
            old = src.read(count)
            new = tgt.read(count)
            if len(old) != count or len(new) != count:
                raise OSError(f"short read at {position:#x}")

            if old != new:
                index = 0
                while index < count:
                    if old[index] == new[index]:
                        index += 1
                        continue
                    end = index + 1
                    while end < count and old[end] != new[end]:
                        end += 1
                    start_abs = position + index
                    end_abs = position + end
                    if ranges and start_abs <= ranges[-1][1] + merge_gap:
                        ranges[-1] = (ranges[-1][0], end_abs)
                    else:
                        ranges.append((start_abs, end_abs))
                    index = end

            position += count
            if position and position % (256 * 1024 * 1024) == 0:
                print(f"  scanned {position / (1024 ** 3):.2f} GiB; {len(ranges)} ranges", flush=True)

    if target_size > common_size:
        # Bytes below the common end do not exist in the source, so they must
        # all be written.  Keep this as one range even when it is much larger
        # than the merge gap.
        if ranges and common_size <= ranges[-1][1] + merge_gap:
            ranges[-1] = (ranges[-1][0], target_size)
        else:
            ranges.append((common_size, target_size))

    return ranges


def build_patch(source: Path, target: Path, output: Path, merge_gap: int) -> None:
    source_size = source.stat().st_size
    target_size = target.stat().st_size
    if source_size <= 0 or target_size <= 0:
        raise ValueError("both images must be non-empty")
    if merge_gap < 0:
        raise ValueError("--merge-gap must be zero or greater")

    print(f"source: {source} ({source_size:,} bytes)")
    print(f"target: {target} ({target_size:,} bytes)")
    print("hashing both images ...")
    source_hash = hash_file(source)
    target_hash = hash_file(target)
    print("scanning for differing ranges ...")
    ranges = scan_ranges(source, target, merge_gap)

    if not ranges:
        raise ValueError("the images are identical; there is nothing to patch")
    for start, end in ranges:
        if start < 0 or end <= start or end > target_size:
            raise ValueError(f"invalid generated range {start:#x}..{end:#x}")
    print(f"changed ranges: {len(ranges)}; changed bytes: {sum(end - start for start, end in ranges):,}")

    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".part")
    try:
        with temp.open("wb") as out, target.open("rb") as tgt:
            out.write(
                HEADER.pack(
                    MAGIC,
                    FORMAT_VERSION,
                    0,
                    source_size,
                    target_size,
                    source_hash,
                    target_hash,
                    len(ranges),
                )
            )
            for index, (start, end) in enumerate(ranges, 1):
                length = end - start
                if length > 0xFFFFFFFF:
                    raise ValueError(f"range {index} is too large")
                tgt.seek(start)
                data = tgt.read(length)
                if len(data) != length:
                    raise OSError(f"short read from target at {start:#x}")
                compressed = zlib.compress(data, 9)
                out.write(SEGMENT_HEADER.pack(start, length, len(compressed)))
                out.write(compressed)
                if index % 50 == 0 or index == len(ranges):
                    print(f"  encoded {index}/{len(ranges)}", flush=True)
        temp.replace(output)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass

    print(f"OK: {output} ({output.stat().st_size:,} bytes)")
    print(f"source sha256: {source_hash.hex()}")
    print(f"target sha256: {target_hash.hex()}")
    print("verify the release with: python culdcept_patch.py info " + str(output))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a CDP1 patch for Culdcept 2.")
    parser.add_argument("source", type=Path, help="pristine Culdcept (USA) ISO")
    parser.add_argument("target", type=Path, help="finished review ISO")
    parser.add_argument("output", type=Path, help="CDP1 patch to create")
    parser.add_argument(
        "--merge-gap",
        type=int,
        default=DEFAULT_MERGE_GAP,
        help=f"merge changed ranges separated by at most this many bytes (default: {DEFAULT_MERGE_GAP})",
    )
    args = parser.parse_args(argv)
    try:
        build_patch(args.source, args.target, args.output, args.merge_gap)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
