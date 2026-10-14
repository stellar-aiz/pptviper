"""本番公開のタグと配布版の一致を確認する。"""

import os
import re
import tomllib
from pathlib import Path


def check_release(event: str, ref: str, version: str) -> None:
    if (
        event != "push"
        or re.fullmatch(r"refs/tags/v[0-9]+\.[0-9]+\.[0-9]+", ref) is None
    ):
        raise ValueError("本番公開には vX.Y.Z 形式のタグの push が必要です")
    if ref.removeprefix("refs/tags/v") != version:
        raise ValueError("タグとパッケージのバージョンが一致しません")


if __name__ == "__main__":
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    check_release(
        os.environ["GITHUB_EVENT_NAME"],
        os.environ["GITHUB_REF"],
        project["project"]["version"],
    )
    print("公開タグとパッケージのバージョンが一致しました")
