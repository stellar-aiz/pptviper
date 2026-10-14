"""Validate the production release tag against the package version."""

import os
import re
import tomllib
from pathlib import Path


def check_release(event: str, ref: str, version: str) -> None:
    if (
        event != "push"
        or re.fullmatch(r"refs/tags/v[0-9]+\.[0-9]+\.[0-9]+", ref) is None
    ):
        raise ValueError("Production publishing requires a vX.Y.Z tag push")
    if ref.removeprefix("refs/tags/v") != version:
        raise ValueError("Tag and package versions do not match")


if __name__ == "__main__":
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    check_release(
        os.environ["GITHUB_EVENT_NAME"],
        os.environ["GITHUB_REF"],
        project["project"]["version"],
    )
    print("Release tag matches the package version")
