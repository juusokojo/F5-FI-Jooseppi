"""Extract one directory tree from a .deb package without root, dpkg or zstd binaries.

    python extract_deb_dir.py PACKAGE.deb usr/lib/voikko DEST

Writes DEST/voikko/... (the last path component of the wanted directory is kept). Handles the ar container and
gz/xz/zst compressed data members; zst needs the PyPI package `zstandard`."""
import io
import os
import sys
import tarfile


def ar_members(path):
    with open(path, "rb") as f:
        if f.read(8) != b"!<arch>\n":
            raise SystemExit(f"{path}: not an ar archive")
        while True:
            head = f.read(60)
            if len(head) < 60:
                return
            name = head[:16].decode().strip().rstrip("/")
            size = int(head[48:58])
            yield name, f.read(size)
            if size % 2:
                f.read(1)


def open_tar(name, data):
    if name.endswith(".zst"):
        import zstandard  # noqa: PLC0415

        data = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data)).read()
        return tarfile.open(fileobj=io.BytesIO(data))
    return tarfile.open(fileobj=io.BytesIO(data))  # gz, xz, bz2 are detected by tarfile


def main(deb, wanted, dest):
    wanted = wanted.strip("/")
    prefix = os.path.dirname(wanted)
    n = 0
    for name, data in ar_members(deb):
        if not name.startswith("data.tar"):
            continue
        with open_tar(name, data) as tar:
            for m in tar.getmembers():
                p = m.name.lstrip("./")
                if not (p == wanted or p.startswith(wanted + "/")):
                    continue
                m.name = os.path.relpath(p, prefix)
                tar.extract(m, dest, filter="data")
                n += 1
    if not n:
        raise SystemExit(f"{wanted}: nothing found in {deb}")
    print(f"extracted {n} entries to {dest}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
