"""Build the read-only media rootfs from trusted image binaries and their ELF deps."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
for directory in ("usr/bin", "proc", "dev", "tmp", "job"):
    (root / directory).mkdir(parents=True, exist_ok=True)
# glibc hosts may use /usr/lib64 through their linker cache. Alpine/musl does not
# need it; retaining it when present also permits running the integration tests.
cache = Path("/etc/ld.so.cache")
if cache.exists():
    (root / "etc").mkdir(exist_ok=True)
    shutil.copy2(cache, root / "etc/ld.so.cache")
for tool in ("ffmpeg", "ffprobe", "opusinfo", "opusdec"):
    binary = Path(shutil.which(tool) or f"/usr/bin/{tool}")
    dependencies = subprocess.run(  # noqa: S603 - trusted image executables only
        ["ldd", str(binary)],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    paths = {str(binary), *re.findall(r"/[^\s()]+", dependencies.stdout)}
    for source in paths:
        destination = root / source.lstrip("/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Dereference symlinks so their targets cannot point outside this rootfs.
        shutil.copy2(source, destination)
    destination = root / "usr/bin" / tool
    if destination != root / str(binary).lstrip("/"):
        shutil.copy2(binary, destination)
