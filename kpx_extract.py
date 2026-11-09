#!/usr/bin/env python3
"""
kpx_extract.py - extractor for the "\x02KPX" archive format used by the
Angry Birds Transformers .obb (and the .pak files nested inside it).

Usage:
    python kpx_extract.py main_24100_com_rovio_angrybirdstransformers.obb out_dir
    python kpx_extract.py <obb> --list          # print the tree, write nothing
    python kpx_extract.py <obb> --test          # decompress everything, write nothing

Format (all little-endian u32):
  header (0x14): magic 02 'K' 'P' 'X' | num_dirs | num_files | strtab_size | flags(1)
  num_dirs  * 32-byte dir records
  num_files * 32-byte file records
  strtab (NUL-separated names), then file data
Dir record : [name_off, 0, first_file, 0, first_subdir, 0, num_files, num_subdirs]
File record: [name_off, 0, size, offset, compressed_flag, 0, compressed_size, 0]
  - offset is relative to the start of this archive (the OBB, or the .pak chunk)
  - if compressed_flag == 1 the data is a plain zlib stream of compressed_size
    bytes that inflates to `size` bytes; otherwise `size` bytes are stored raw
  - dir 0 is the root. Files of a dir are first_file .. first_file+num_files-1,
    subdirs are first_subdir .. first_subdir+num_subdirs-1.
Each .pak inside the OBB is itself a KPX archive, so extraction recurses.
"""
import os
import struct
import sys
import zlib

MAGIC = b"\x02KPX"


class Kpx:
    def __init__(self, fh, base, length):
        self.fh, self.base, self.length = fh, base, length
        fh.seek(base)
        hdr = fh.read(0x14)
        if hdr[:4] != MAGIC:
            raise ValueError("not a KPX archive at 0x%x" % base)
        self.nd, self.nf, self.ns, _ = struct.unpack("<4I", hdr[4:20])
        self.dirs = [struct.unpack("<8I", fh.read(32)) for _ in range(self.nd)]
        self.files = [struct.unpack("<8I", fh.read(32)) for _ in range(self.nf)]
        self.strtab = fh.read(self.ns)

    def name(self, off):
        end = self.strtab.index(b"\0", off)
        return self.strtab[off:end].decode("utf-8", "replace")

    def walk(self, di=0, prefix=""):
        """Yield (path, file_record) for every file under dir index di."""
        d = self.dirs[di]
        first_file, first_sub, nfiles, nsubs = d[2], d[4], d[6], d[7]
        for i in range(first_file, first_file + nfiles):
            r = self.files[i]
            yield prefix + self.name(r[0]), r
        for s in range(first_sub, first_sub + nsubs):
            yield from self.walk(s, prefix + self.name(self.dirs[s][0]) + "/")

    def read(self, rec):
        size, off, comp, csize = rec[2], rec[3], rec[4], rec[6]
        self.fh.seek(self.base + off)
        if comp == 1:
            data = zlib.decompress(self.fh.read(csize))
            if len(data) != size:
                raise ValueError("size mismatch %d != %d" % (len(data), size))
            return data
        return self.fh.read(size)


def process(fh, base, length, outdir, mode, label=""):
    """Returns (files_ok, files_bad, bytes_out)."""
    arc = Kpx(fh, base, length)
    ok = bad = total = 0
    for path, rec in arc.walk():
        full = label + path
        stored_raw = rec[4] != 1
        # a stored (uncompressed) entry that is itself a KPX archive -> recurse
        if stored_raw and rec[2] >= 4:
            fh.seek(base + rec[3])
            if fh.read(4) == MAGIC:
                sub = os.path.join(outdir, os.path.splitext(path)[0]) if outdir else None
                o, b, t = process(fh, base + rec[3], rec[2], sub, mode, full + "/")
                ok, bad, total = ok + o, bad + b, total + t
                continue
        try:
            data = arc.read(rec)
        except Exception as e:  # noqa: BLE001
            print("FAIL", full, e)
            bad += 1
            continue
        ok += 1
        total += len(data)
        if mode == "list":
            print("%10d  %s" % (len(data), full))
        elif mode == "extract":
            dst = os.path.join(outdir, path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as w:
                w.write(data)
    return ok, bad, total


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    obb, arg = sys.argv[1], sys.argv[2]
    mode = {"--list": "list", "--test": "test"}.get(arg, "extract")
    outdir = arg if mode == "extract" else None
    with open(obb, "rb") as fh:
        size = os.fstat(fh.fileno()).st_size
        ok, bad, total = process(fh, 0, size, outdir, mode)
    print("files ok: %d  failed: %d  bytes: %d" % (ok, bad, total))


if __name__ == "__main__":
    main()
