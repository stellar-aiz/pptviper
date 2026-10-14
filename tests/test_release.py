"""公開を許可するイベント・タグを確認する。"""

import pytest

from scripts.check_release import check_release


def test_matching_release() -> None:
    check_release("push", "refs/tags/v0.1.0", "0.1.0")


@pytest.mark.parametrize(
    ("event", "ref", "version"),
    [
        ("push", "refs/heads/main", "0.1.0"),
        ("pull_request", "refs/tags/v0.1.0", "0.1.0"),
        ("workflow_dispatch", "refs/tags/v0.1.0", "0.1.0"),
        ("push", "refs/tags/v0.1.1", "0.1.0"),
        ("push", "refs/tags/v0.1.0rc1", "0.1.0"),
    ],
)
def test_reject_other_releases(event: str, ref: str, version: str) -> None:
    with pytest.raises(ValueError):
        check_release(event, ref, version)
