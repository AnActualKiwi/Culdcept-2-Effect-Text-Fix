#!/usr/bin/env python3
"""Apply a Culdcept 2 Effect Text Fix patch to a pristine disc image.

The patch is deliberately a small, self-contained binary delta.  It stores only
the byte ranges that differ from the pristine Redump image; applying it does not
need this project, a Python package, an emulator, or any intermediate ISO.

Patch format (CDP1)
-------------------
Header, little-endian:
    4s  magic                 b"CDP1"
    H   format version        1
    H   flags                 0
    Q   source size
    Q   target size
    32s source SHA-256
    32s target SHA-256
    I   segment count

Each segment:
    Q   absolute byte offset in the source/target
    Q   uncompressed length
    I   compressed length
    ... zlib-compressed target bytes

Segments are sorted, non-overlapping, and must fit inside the target size.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import sys
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"CDP1"
FORMAT_VERSION = 1
HEADER = struct.Struct("<4sHHQQ32s32sI")
SEGMENT_HEADER = struct.Struct("<QQI")
MAX_SEGMENT_COMPRESSED = 1 << 30
COPY_CHUNK = 8 * 1024 * 1024


class PatchError(Exception):
    """A malformed patch, wrong source image, or failed verification."""


@dataclass(frozen=True)
class Patch:
    source_size: int
    target_size: int
    source_sha256: bytes
    target_sha256: bytes
    segments: tuple[tuple[int, bytes], ...]


def sha256_file(path: Path, *, label: str | None = None) -> bytes:
    """Return the SHA-256 of a file, reading it in bounded chunks."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(COPY_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    if label:
        print(f"{label}: {size:,} bytes  sha256 {digest.hexdigest()}")
    return digest.digest()


def read_exact(handle, length: int, what: str) -> bytes:
    data = handle.read(length)
    if len(data) != length:
        raise PatchError(f"truncated patch while reading {what}")
    return data


def load_patch(path: Path) -> Patch:
    """Read and fully validate a CDP1 patch without touching an ISO."""
    if not path.is_file():
        raise PatchError(f"patch not found: {path}")
    with path.open("rb") as handle:
        raw = read_exact(handle, HEADER.size, "header")
        magic, version, flags, source_size, target_size, source_hash, target_hash, count = HEADER.unpack(raw)
        if magic != MAGIC:
            raise PatchError("not a CDP1 patch (bad magic)")
        if version != FORMAT_VERSION:
            raise PatchError(f"unsupported patch format version {version}")
        if flags != 0:
            raise PatchError(f"unsupported patch flags {flags:#x}")
        if source_size <= 0 or target_size <= 0:
            raise PatchError("patch has an invalid image size")
        if count == 0:
            raise PatchError("patch has no byte ranges")
        if count > 1_000_000:
            raise PatchError("patch has an implausible number of ranges")

        segments: list[tuple[int, bytes]] = []
        previous_end = 0
        for index in range(count):
            offset, raw_length, compressed_length = SEGMENT_HEADER.unpack(
                read_exact(handle, SEGMENT_HEADER.size, f"segment {index} header")
            )
            if raw_length == 0:
                raise PatchError(f"segment {index} has zero length")
            if compressed_length == 0 or compressed_length > MAX_SEGMENT_COMPRESSED:
                raise PatchError(f"segment {index} has an invalid compressed length")
            if offset < previous_end:
                raise PatchError(f"segment {index} overlaps or is out of order")
            if offset + raw_length > target_size:
                raise PatchError(f"segment {index} extends past the target image")
            compressed = read_exact(handle, compressed_length, f"segment {index} data")
            try:
                data = zlib.decompress(compressed)
            except zlib.error as exc:
                raise PatchError(f"segment {index} is not valid zlib data: {exc}") from exc
            if len(data) != raw_length:
                raise PatchError(
                    f"segment {index} expands to {len(data)} bytes, expected {raw_length}"
                )
            segments.append((offset, data))
            previous_end = offset + raw_length

        trailing = handle.read(1)
        if trailing:
            raise PatchError("patch has trailing data after the last segment")

    return Patch(
        source_size=source_size,
        target_size=target_size,
        source_sha256=source_hash,
        target_sha256=target_hash,
        segments=tuple(segments),
    )


def check_source(source: Path, patch: Patch) -> None:
    if not source.is_file():
        raise PatchError(f"source image not found: {source}")
    size = source.stat().st_size
    if size != patch.source_size:
        raise PatchError(
            f"source image is {size:,} bytes; this patch requires {patch.source_size:,} bytes"
        )
    digest = sha256_file(source, label="source")
    if digest != patch.source_sha256:
        raise PatchError(
            "source image SHA-256 does not match the pristine Redump image\n"
            f"  expected {patch.source_sha256.hex()}\n"
            f"  actual   {digest.hex()}"
        )


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return a.resolve() == b.resolve()


def apply_patch(source: Path, patch_path: Path, output: Path, *, force: bool = False) -> None:
    """Verify the source, apply all ranges, verify the result, then publish it."""
    patch = load_patch(patch_path)
    check_source(source, patch)

    if _same_file(source, output):
        raise PatchError("the output path must differ from the source image")
    if _same_file(patch_path, output):
        raise PatchError("the output path must differ from the patch file")
    if output.exists() and not force:
        raise PatchError(f"output already exists: {output} (use --force to replace it)")

    output.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output.parent,
            prefix=output.name + ".",
            suffix=".part",
            delete=False,
        ) as out:
            temp_name = Path(out.name)
            with source.open("rb") as src:
                shutil.copyfileobj(src, out, COPY_CHUNK)

            print(f"applying {len(patch.segments)} byte ranges ...")
            for index, (offset, data) in enumerate(patch.segments, 1):
                out.seek(offset)
                written = out.write(data)
                if written != len(data):
                    raise PatchError(f"short write for segment {index}")
                if index % 50 == 0 or index == len(patch.segments):
                    print(f"  {index}/{len(patch.segments)}")

            out.truncate(patch.target_size)
            out.flush()
            os.fsync(out.fileno())

        actual_size = temp_name.stat().st_size
        if actual_size != patch.target_size:
            raise PatchError(
                f"output is {actual_size:,} bytes; expected {patch.target_size:,}"
            )
        digest = sha256_file(temp_name, label="output")
        if digest != patch.target_sha256:
            raise PatchError(
                "output SHA-256 does not match the patch target\n"
                f"  expected {patch.target_sha256.hex()}\n"
                f"  actual   {digest.hex()}"
            )
        if output.exists():
            output.unlink()
        os.replace(temp_name, output)
        temp_name = None
        print(f"OK: {output}")
    finally:
        if temp_name is not None:
            try:
                temp_name.unlink()
            except FileNotFoundError:
                pass


def describe_patch(path: Path) -> None:
    patch = load_patch(path)
    print(f"patch:      {path}")
    print(f"source size: {patch.source_size:,}")
    print(f"target size: {patch.target_size:,}")
    print(f"source sha:  {patch.source_sha256.hex()}")
    print(f"target sha:  {patch.target_sha256.hex()}")
    print(f"ranges:      {len(patch.segments)}")
    print(f"changed:     {sum(len(data) for _, data in patch.segments):,} bytes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply a Culdcept 2 Effect Text Fix patch to a pristine SLUS-20774 ISO."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply_parser = subparsers.add_parser("apply", help="patch a pristine ISO")
    apply_parser.add_argument("source", type=Path, help="pristine Culdcept (USA) ISO")
    apply_parser.add_argument("patch", type=Path, help="CDP1 patch file")
    apply_parser.add_argument("output", type=Path, help="new patched ISO path")
    apply_parser.add_argument("--force", action="store_true", help="replace an existing output")

    info_parser = subparsers.add_parser("info", help="inspect a patch without applying it")
    info_parser.add_argument("patch", type=Path, help="CDP1 patch file")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "apply":
            apply_patch(args.source, args.patch, args.output, force=args.force)
        elif args.command == "info":
            describe_patch(args.patch)
        else:  # pragma: no cover
            parser.error("unknown command")
    except (PatchError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
