"""Verify distribution metadata, licensing, and installation in isolation."""

import os
import subprocess
import tarfile
import tempfile
import tomllib
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile


def main() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    (wheel,) = Path("dist").glob("*.whl")
    (sdist,) = Path("dist").glob("*.tar.gz")
    with ZipFile(wheel) as archive:
        (metadata_name,) = (n for n in archive.namelist() if n.endswith("/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        assert metadata["License-Expression"] == "MIT"
        assert metadata["Version"] == version
        assert sorted(metadata.get_all("Requires-Dist", [])) == sorted(
            project["project"]["dependencies"]
        )
        assert "pptviper/report.schema.json" in archive.namelist()
        assert any(n.endswith("/LICENSE") for n in archive.namelist())
    with tarfile.open(sdist) as archive:
        assert any(n.endswith("/LICENSE") for n in archive.getnames())
    print(
        f"Distributions verified: {wheel.name}, {sdist.name}; "
        "MIT; declared runtime dependencies and report schema verified",
        flush=True,
    )
    with tempfile.TemporaryDirectory(prefix="pptviper-dist-") as directory:
        env = Path(directory) / "venv"
        subprocess.run(["uv", "venv", str(env)], check=True)
        binaries = env / ("Scripts" if os.name == "nt" else "bin")
        python = binaries / ("python.exe" if os.name == "nt" else "python")
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                str(wheel.resolve()),
            ],
            check=True,
        )
        executable = binaries / ("pptviper.exe" if os.name == "nt" else "pptviper")
        result = subprocess.run(
            [str(executable), "--version"],
            cwd=directory,
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == f"pptviper {version}"
        print(result.stdout.strip())
        subprocess.run(
            [str(python), "-c", "import pptviper; print(pptviper.__version__)"],
            cwd=directory,
            check=True,
        )


if __name__ == "__main__":
    main()
