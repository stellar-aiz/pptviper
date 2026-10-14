# pptviper

A Python library and CLI for finding visual problems in PPTX files without
rendering slides. It prioritizes lightweight, best-effort analysis, saved
presentation data, and explicit uncertainty.
The specification lives in [Issue #1](https://github.com/stellar-aiz/pptviper/issues/1).

The initial inspector supports `off-slide`, `invalid-ooxml`, and `unreadable-part`.
It resolves saved geometry and inheritance and reports unsupported content rather
than treating it as a clean result. Text measurement and the remaining visual
rules are subsequent work.

## Inspect a presentation

```sh
pptviper slides.pptx                    # JSON on stdout
pptviper slides.pptx --format text      # Human-readable summary
pptviper slides.pptx --config lint.toml
```

```python
from pptviper import inspect

report = inspect("slides.pptx")
print(report.to_json())
print(report.exit_code)
```

Exit priority is **3 > 1 > 2 > 0**: unreadable input or invalid configuration,
unsuppressed findings, unresolved checks, then success. Suppressed findings stay
in the report. They do not hide unreadability or uncertainty.

See [inspection](docs/inspection.md) for configuration, numerical precision,
coverage, supported inheritance, and the effective-bounds extension point.

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
installation and publishing are separate operations. The only runtime dependency
is defusedxml (PSF license), used to reject XML entities and DTDs. python-pptx,
image libraries pulled in by its fixtures, and JSON Schema validation are
**development-only** dependencies.

See [AGENTS.md](AGENTS.md) for contribution rules and
[publishing](docs/publishing.md) for release instructions.
