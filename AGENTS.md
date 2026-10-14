# Repository guidelines

## Specification and language

- English is the common language of this repository. Use English for documentation,
  comments, user-facing application messages, commits, issues, and pull requests.
  Conversation with the user may be in English or Japanese; keep repository
  artifacts in English regardless of the conversation language.
- The authoritative specification is
  https://github.com/stellar-aiz/pptviper/issues/1.
  Update the epic before changing rule IDs, behavior, or acceptance criteria.
- Prioritize lightweight, best-effort analysis, saved presentation data, and
  explicit uncertainty.
- Use Conventional Commits in English. Squash pull requests when merging.

## Branches and dependencies

- Submit implementation changes through a branch and pull request. Do not commit
  directly to main.
- For an empty repository with no remote branches, the first commit may be an
  empty commit on main. All implementation changes must follow in a pull request.
- Runtime dependencies must use permissive licenses such as MIT, BSD, or
  Apache-2.0. Do not add copyleft dependencies. List each added dependency, its
  license, and its purpose in the pull request.
- Commit uv.lock and keep development dependencies separate from runtime ones.
- Before pushing, verify that .gitignore excludes credentials, environment files,
  and virtual environments.
- Complete the PR template's summary, validation, language check, risks, and links.

## Tests

```sh
uv sync --locked
uv run pytest
uv run ruff check
uv run ruff format --check
uv run pyright
uv build
uv run python scripts/verify_dist.py
```

- On Windows PowerShell, set `$env:PYTHONUTF8 = "1"` before running checks.
- The default pytest configuration blocks socket access inside the tested Python
  process. Network-blocking tests expect the blocking exception and pass without
  contacting a real network endpoint.
- Dependency installation, publishing, and CI infrastructure traffic are outside
  this scope. Blocking is not an OS-wide guarantee for subprocesses or native code.
- Generate PPTX fixtures during tests instead of committing binaries. Exceptions
  require a documented creation procedure when runtime generation is impossible.
- tests/pptx_factory.py provides single_shape_pptx, which takes integer EMU
  coordinates and dimensions. python-pptx is a development-only dependency.
- Use replace_part to replace an existing ZIP part, or pass None to delete it.
  Use truncate_zip to truncate the archive. Add specialized fixtures with the issue
  that needs them.
- Follow docs/publishing.md for releases. Do not automatically close an issue when
  its TestPyPI publication check is still outstanding.
