# Package and release preparation

The current local adoption draft is **0.3.0a1**. It is an alpha, and no PyPI
publication is claimed. The project already builds a Python wheel and source
archive; the draft adds a public library API and qualification of installed wheels.
The MCP dependency floor is 1.30. A clean install with the previous 1.20 floor
failed during import against current Pydantic because that SDK referenced a removed
internal function. The floor was raised to the version qualified with current
dependencies instead of imposing an unrelated Pydantic pin.
The version has one source: `src/agent_relay/__init__.py`, read by Hatchling.

## Build and verify locally

```sh
uv sync --locked --python 3.12 --extra models
uv run --extra models pytest -q
uv run --extra models ruff check .
uv run --extra models ruff format --check .
uv build
uvx --from 'twine==7.0.0' twine check dist/*
```

Use a clean output directory for each release so old wheels are not accidentally
qualified or uploaded. For an installation check, use the wheel for the exact
version just built:

```sh
uv venv .wheel-venv --python 3.12
uv pip install --python .wheel-venv/bin/python dist/agent_relay-0.3.0a1-py3-none-any.whl
.wheel-venv/bin/python scripts/qualify_install.py
```

The qualification runs outside the source checkout and refuses editable installs.
It checks metadata/version, real stdio MCP, external-peer setup, read-only
diagnostics, exported-server startup, and the Python API. It clears provider
binaries from command PATH and performs no model calls. Repeat in a separate
environment with the wheel's `models` extra when qualifying optional API support;
SDK/local-endpoint tests and live CLI tests remain separate evidence.
CI also builds and qualifies the wheel in each Python 3.12/3.13 job: the base wheel,
or the wheel with its `models` extra in the jobs that select it.
The release workflow repeats base and optional wheel qualification before upload.

## Future publication

[Python package-name normalization](https://packaging.python.org/en/latest/specifications/name-normalization/)
maps `agent_relay` to `agent-relay`. A public PyPI lookup for `agent-relay` returned
404 on 10 October 2026; that does **not** reserve or guarantee availability.
The separate name [agentrelay](https://pypi.org/project/agentrelay/) belongs to
another project. Recheck name ownership at publication time. Keep source install
instructions authoritative until this project's actual release is available.

The included `publish.yml` is **manual only** and defaults to TestPyPI. It does not
run on push or tag creation. Before using it:

1. Create your PyPI/TestPyPI account and a pending Trusted Publisher for the exact
   project name, repository owner/name, workflow filename `publish.yml`, and
   environment `testpypi` or `pypi`.
2. Configure the corresponding GitHub environment with release reviewers. The
   workflow references an environment; reviewer protection must be configured in
   GitHub and is not established by the YAML file.
3. Review the exact source revision, dependency changes, package metadata, license,
   test results, artifact contents and hashes. Select an immutable tag/ref for the
   manual run; the workflow checks version agreement and qualifies the built wheel.
4. Publish the alpha to TestPyPI first, verify it, and only then deliberately choose
   PyPI for an approved release. Update the README to the verified install command
   after publication, not before.

[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
uses GitHub OIDC instead of a long-lived upload token. Only the upload job receives
`id-token: write`; the build job has read-only repository permissions. Build outputs
are passed as artifacts, and the publish action is pinned to a verified release revision.
No publisher, environment, remote release or upload is configured by local edits.

This workflow is prepared source, not evidence that its remote jobs or a PyPI
upload succeeded. Never upload private workspace config, `.local`, `.planning`,
credentials or provider transcripts. Built artifacts must contain only distributable
source/docs and package metadata.
