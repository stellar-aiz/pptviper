# Publishing

## Administrator setup

1. Verify that the name pptviper is available and that you have the necessary
   permissions on both PyPI and TestPyPI.
2. Register a Trusted Publisher on each service. Use a Pending Publisher when
   creating a new project.

| Setting | PyPI | TestPyPI |
|---|---|---|
| Owner | stellar-aiz | stellar-aiz |
| Repository | pptviper | pptviper |
| Workflow | publish.yml | publish.yml |
| Environment | pypi | testpypi |

3. Create the pypi and testpypi environments in GitHub. Production publishing uses
   release tags; test publishing uses main. Do not store API tokens.

## TestPyPI acceptance check

After the code is merged into main and the publishers are configured, manually
run the Publish workflow from main. Selecting another branch will not publish.

```sh
gh workflow run publish.yml --ref main
```

After publication succeeds, install that version into an independent environment.
The initial version is 0.1.0.

```sh
uv venv /tmp/pptviper-testpypi
uv pip install --python /tmp/pptviper-testpypi/bin/python --no-deps \
  --index-url https://test.pypi.org/simple/ pptviper==0.1.0
/tmp/pptviper-testpypi/bin/pptviper --version
```

On Windows, create the environment in a suitable temporary directory and replace
bin/python and bin/pptviper with Scripts/python.exe and Scripts/pptviper.exe.
No additional package index is needed because there are no runtime dependencies.

Record the published commit, version, Actions run URL, and installation result in
Issue #2. Keep the issue open until AC-3 is verified. If administrator setup is
incomplete, record the missing configuration. Documentation alone does not
satisfy AC-3. A published file cannot be uploaded again; increment the version
when publishing changed contents.

## Production release

Merge a PR updating the version in pyproject.toml, then push a matching vX.Y.Z tag.
The workflow checks the tag format and version before publishing. Mismatched
tags, ordinary branch updates, pull requests, and manual runs do not publish to
production. PyPI and TestPyPI require separate publisher configuration.
Production publication is not part of Issue #2's acceptance check.

- [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
- [Publishing with uv](https://docs.astral.sh/uv/guides/publish/)
