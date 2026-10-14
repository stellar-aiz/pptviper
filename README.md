# pptviper

A Python library and CLI for finding visual problems in PPTX files without
rendering slides. It prioritizes lightweight, best-effort analysis, saved
presentation data, and explicit uncertainty.
The specification lives in [Issue #1](https://github.com/stellar-aiz/pptviper/issues/1).

Only the development foundation is implemented so far. Presentation inspection
will be added in subsequent issues.

## Development

Python 3.12 or later and uv are required. CI checks Python 3.12, 3.13, and 3.14
on Linux, macOS, and Windows (nine combinations).

```sh
uv sync --locked
uv run pptviper --version
uv run pytest
uv run ruff check
uv run ruff format --check
uv run pyright
uv build
uv run python scripts/verify_dist.py
```

On Windows PowerShell, set `$env:PYTHONUTF8 = "1"` before running checks for
consistent Unicode handling. CI uses the same setting.

Tests block network access through Python sockets by default. Dependency
installation and publishing are separate operations. There are no runtime
dependencies; development dependencies include python-pptx for test fixtures.

See [AGENTS.md](AGENTS.md) for contribution rules and
[publishing](docs/publishing.md) for release instructions.
