# pywrangler / uv vendoring bug on Windows

## Symptom

`uv run pywrangler dev` (or `sync`) crashes the Worker at startup with something like:

```
ModuleNotFoundError: No module named 'jinja2'
```

or the same for any other declared dependency. `python_modules/` ends up empty
(just `pyvenv.cfg`) even though `sync` reports `Sync process completed successfully.`
The `Vendored Modules` size in the `wrangler dev` startup table shows `0.01 KiB`.

## Root cause

`pywrangler sync` vendors dependencies by running:

```
uv pip install --python <path-to-.venv-workers/pyodide-venv> --no-build -r pylock.toml --preview-features pylock
```

On Windows, `uv` mis-resolves the Pyodide/emscripten cross-target's site-packages
path to a leading double slash, e.g. `//lib/python3.13/site-packages`. Windows
parses `//...` as the start of a UNC network path, so directory creation fails
with `os error 53` ("The network path was not found"). This failure happens
inside the *inner* `uv pip install` subprocess; `pywrangler`'s own wrapper
(`_install_requirements_to_vendor` in `pywrangler/sync.py`) doesn't propagate
it as a hard error under some invocation paths, so `sync` reports success while
having installed nothing.

Confirmed present in `uv` 0.12.2 and 0.12.3 — this is a Windows-only bug in `uv`
(or in how `pywrangler` invokes it for the emscripten cross-target), not
something fixable from this repo's own code.

There's a second, separate quirk: installing the *whole* lockfile in one batch
occasionally causes `uv` to silently skip a handful of entries (observed with
`jinja2`/`markupsafe`, both partly/fully sourced from the Pyodide CDN in
`pylock.toml`) — no error, they just don't land. The fix below detects and
retries those individually.

## Fix

Installing with `--target <dir>` and an explicit `--python-platform` avoids the
broken site-packages resolution entirely (it doesn't go through the venv
sysconfig scheme lookup at all):

```
uv pip install --target python_modules \
  --python-platform wasm32-pyodide2025 --python-version 3.13 \
  --no-build --extra-index-url https://index.pyodide.org/0.28.3 \
  --index-strategy unsafe-best-match \
  -r pylock.toml --preview-features pylock
```

`--python-platform` values used here: `wasm32-pyodide2024` for Python 3.12,
`wasm32-pyodide2025` for 3.13/3.14 (matches `pywrangler`'s own
`get_pyodide_index()` version mapping).

The actual fix is a patch to the **installed** `pywrangler` package —
`_install_requirements_to_vendor()` in:

```
.venv/Lib/site-packages/pywrangler/sync.py
```

Changes made there:

1. Added a `get_pyodide_index` import from `.utils`.
2. Added a helper `_get_pyodide_platform_tag()` that maps `get_python_version()`
   → the `--python-platform` tag (see above).
3. Rewrote `_install_requirements_to_vendor()` to install straight into
   `python_modules` via `--target` + `--python-platform` + `--python-version`
   + `--extra-index-url <pyodide index>`, instead of `--python <pyodide-venv>`
   + the old rmtree/copytree dance from the pyodide venv's site-packages.
4. After the batch install, it scans `python_modules/*.dist-info` against
   `plan.requirements` (from `pylock.toml`) and re-installs (with `--no-deps`,
   pinned to the locked version) any package that didn't land, working around
   the batch-skip quirk.

Full replacement function, for reapplying after this gets clobbered:

```python
def _get_pyodide_platform_tag() -> str:
    """uv's --python-platform tag for the Pyodide version this project targets."""
    match get_python_version():
        case "3.12":
            return "wasm32-pyodide2024"
        case "3.13" | "3.14":
            return "wasm32-pyodide2025"


def _install_requirements_to_vendor(
    plan: InstallPlan, allow_build: bool = False
) -> str | None:
    """Install packages to the Pyodide vendor directory from pylock.toml.

    Installs directly into ``python_modules`` via ``uv pip install --target``
    with an explicit ``--python-platform``, rather than ``--python <pyodide venv>``.
    The latter mis-resolves the Pyodide/emscripten site-packages path to a leading
    ``//`` (e.g. ``//lib/python3.13/site-packages``), which Windows parses as a UNC
    network path and fails to create with "os error 53". ``--target`` mode installs
    straight into the given directory without going through that sysconfig lookup.

    By default ``--no-build`` is passed so only prebuilt wheels install. When
    *allow_build* is True, source distributions / local directory sources are
    allowed to build.

    Returns:
        Error message string if installation failed, None if successful.
    """
    vendor_path = get_vendor_modules_path()
    logger.debug(f"Using vendor path: {vendor_path}")

    if len(plan.requirements) == 0:
        logger.warning(
            f"Requirements list is empty. No dependencies to install in {vendor_path}."
        )
        return None

    if vendor_path.is_dir():
        shutil.rmtree(vendor_path)
    vendor_path.mkdir(parents=True, exist_ok=True)
    relative_vendor_path = vendor_path.relative_to(get_project_root())
    logger.info(
        f"Installing packages into [bold]{relative_vendor_path}[/bold]...",
        extra={"markup": True},
    )

    install_cmd = [
        "uv",
        "pip",
        "install",
        "--target",
        str(vendor_path),
        "--python-platform",
        _get_pyodide_platform_tag(),
        "--python-version",
        get_python_version(),
        "--extra-index-url",
        get_pyodide_index(),
        "--index-strategy",
        "unsafe-best-match",
    ]
    if not allow_build:
        install_cmd.append("--no-build")
    else:
        # uv caches built wheels for local sources keyed on their path, so edits
        # to local checkouts wouldn't be picked up. Refresh the build cache for
        # those packages so `sync` always rebuilds them.
        for name in plan.local_packages:
            install_cmd += ["--refresh-package", name]

    result = run_command(
        install_cmd + ["-r", str(plan.lockfile), "--preview-features", "pylock"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return result.stdout.strip()

    # uv's pylock reader has occasionally silently skipped individual entries
    # (seen with CDN-sourced wheels like jinja2/markupsafe) when installing the
    # lockfile in one batch. Detect and retry those individually.
    installed = {
        p.stem.rsplit("-", 1)[0].replace("_", "-").lower()
        for p in vendor_path.glob("*.dist-info")
    }
    missing = [
        (name, version)
        for name, version in plan.requirements
        if name.lower() not in installed
    ]
    for name, version in missing:
        logger.debug(f"Batch install skipped {name}=={version}; installing individually")
        result = run_command(
            install_cmd + ["--no-deps", f"{name}=={version}"],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return result.stdout.strip()

    # Create a pyvenv.cfg file in python_modules to mark it as a virtual environment
    (vendor_path / "pyvenv.cfg").touch()
    _write_sync_token(get_vendor_token_path())

    logger.info(
        f"Packages installed in [bold]{relative_vendor_path}[/bold].",
        extra={"markup": True},
    )
    return None
```

Also update the import block near the top of the same file to include
`get_pyodide_index`:

```python
from .utils import (
    check_uv_version,
    check_wrangler_config,
    find_pyproject_toml,
    get_lockfile_path,
    get_project_root,
    get_pyodide_index,      # <- added
    get_python_version,
    get_pywrangler_config,
    get_pywrangler_version,
    get_uv_pyodide_interp_name,
    run_command,
    temp_requirements_file,
)
```

## Caveat — this patch is NOT durable

The patch lives in `.venv/Lib/site-packages/pywrangler/sync.py`, i.e. inside a
third-party package inside the virtualenv. It will be silently lost whenever
that environment is rebuilt or the package reinstalled/upgraded — `uv sync
--reinstall`, deleting `.venv`, bumping the `workers-py` version, a fresh
clone + `uv sync`, etc.

**If `uv run pywrangler dev` starts throwing `ModuleNotFoundError` again for a
declared dependency, and `python_modules/` is empty (or far smaller than
expected) after `sync` reports success — this is almost certainly the same bug
resurfacing after an env rebuild.** Point Claude at this file to reapply the
patch rather than re-diagnosing from scratch.

## Verifying the fix is in place / worked

```
uv run pywrangler --debug sync --force
```

should end with `SUCCESS  Sync process completed successfully.` **and**
`python_modules/` should contain one directory + `.dist-info` per dependency
(not just `pyvenv.cfg`). Then `uv run pytest tests/ -v` should pass — the test
suite's `conftest.py` starts the server via `uv run pywrangler dev`, so it
exercises this exact path.
