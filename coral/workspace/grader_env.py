"""CORAL-managed grader virtual environment.

Creates and bootstraps `.coral/private/grader_venv/` so that grader code
referenced by `grader.entrypoint` can be imported by a worker subprocess
without polluting CORAL's own venv.

Design:
  - venv lives inside `.coral/private/`, which is already covered by the
    Read deny-rule applied to agent worktrees (worktree.py).
  - The grader venv must be able to `import coral` so user grader packages
    can declare `coral` as a dependency. We replicate whatever install
    method produced the running CORAL by reading PEP 610 `direct_url.json`
    out of coral's dist-info:
      * editable install (dev `uv sync` path) -> `uv pip install -e <path>`
      * git VCS install (the README's `install.sh` -> `uv tool install
        git+...` path) -> `uv pip install git+<url>@<commit_id>`
    Both flavors point the grader venv at the exact same code the host is
    running, so there's no version drift between host and grader.
  - User's `grader.setup` shell commands then run with VIRTUAL_ENV pointed
    at the grader venv, so plain `uv pip install ...` lands in the right
    place.

Venv caching:
  - The built venv is stored in a shared cache directory keyed by a hash
    of the coral install command, grader setup commands, config dir, and
    Python version. Subsequent runs with the same grader config reuse the
    cached venv via a directory junction (Windows) or symlink (Unix),
    avoiding the 300-500 MB per-run overhead.
  - Cache lives at: $LOCALAPPDATA/coral/grader_venvs/<key>/ (Windows)
                    ~/.cache/coral/grader_venvs/<key>/     (Linux/macOS)
  - Falls back to a local (non-cached) build if linking fails.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from urllib.parse import urlparse

from coral.config import GraderConfig
from coral.workspace.repo import _clean_env, run_setup_commands

logger = logging.getLogger(__name__)


def _coral_install_origin() -> dict:
    """Return the PEP 610 install origin recorded in coral's dist-info.

    `direct_url.json` is written by every modern installer (pip >= 19, uv)
    and records what URL and (for VCS) what commit the package was installed
    from. Reading it lets us replicate the running install into the grader
    venv without guessing.

    Raises RuntimeError if the file is missing — that means coral was either
    installed by an installer that doesn't write PEP 610 metadata, or
    something went wrong with the install. In either case the caller can't
    safely replicate it.
    """
    host_site = Path(sysconfig.get_paths()["purelib"])
    dist_infos = list(host_site.glob("coral-*.dist-info"))
    if not dist_infos:
        raise RuntimeError(
            f"No coral-*.dist-info found in {host_site}; cannot determine how CORAL was installed."
        )
    direct_url = dist_infos[0] / "direct_url.json"
    if not direct_url.exists():
        raise RuntimeError(
            f"{direct_url} not found; CORAL was installed by an installer that "
            "does not write PEP 610 metadata. Reinstall with `uv tool install "
            "git+https://github.com/Human-Agent-Society/CORAL.git` or "
            "`git clone ... && uv sync`."
        )
    return json.loads(direct_url.read_text())


def _coral_install_command(origin: dict) -> str:
    """Build the `uv pip install` command that replicates the host coral install."""
    url = origin.get("url")
    if not url:
        raise RuntimeError(f"direct_url.json missing 'url': {origin!r}")

    if origin.get("dir_info", {}).get("editable"):
        # `file:///abs/path` -> `/abs/path` (strip leading `/` on Windows: `/C:/...` -> `C:/...`)
        local_path = urlparse(url).path
        if sys.platform == "win32" and local_path.startswith("/") and len(local_path) > 2 and local_path[2] == ":":
            local_path = local_path[1:]
        return f"uv pip install -q -e {local_path}"

    if "vcs_info" in origin:
        vcs = origin["vcs_info"].get("vcs")
        commit = origin["vcs_info"].get("commit_id")
        if vcs != "git" or not commit:
            raise RuntimeError(
                f"Only git VCS installs are supported; got vcs_info={origin['vcs_info']!r}"
            )
        return f"uv pip install -q git+{url}@{commit}"

    raise RuntimeError(
        f"Unsupported coral install origin (not editable, not VCS): {origin!r}. "
        "Reinstall via `uv tool install git+...` or `uv sync`."
    )


def grader_venv_path(coral_dir: Path) -> Path:
    """Path to the grader venv for a given .coral dir."""
    return coral_dir / "private" / "grader_venv"


def grader_python_path(coral_dir: Path) -> Path:
    """Path to the Python interpreter inside the grader venv."""
    if sys.platform == "win32":
        return grader_venv_path(coral_dir) / "Scripts" / "python.exe"
    return grader_venv_path(coral_dir) / "bin" / "python"


# ---------------------------------------------------------------------------
# Venv cache helpers
# ---------------------------------------------------------------------------

def _platform_cache_dir() -> Path:
    """Return the platform cache directory for shared grader venvs."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "coral" / "grader_venvs"


def _venv_cache_key(coral_install_cmd: str, grader_config: GraderConfig, config_dir: Path) -> str:
    """Stable hash key for a grader venv configuration."""
    parts = [
        coral_install_cmd,
        "\n".join(grader_config.setup or []),
        str(config_dir.resolve()),
        sys.version,
    ]
    return hashlib.sha256("\n---\n".join(parts).encode()).hexdigest()[:20]


def _cached_python_path(cache_venv: Path) -> Path:
    """Path to python inside a cache venv dir."""
    if sys.platform == "win32":
        return cache_venv / "Scripts" / "python.exe"
    return cache_venv / "bin" / "python"


def _make_dir_link(dst: Path, src: Path) -> bool:
    """Link dst → src as a junction (Windows) or symlink (Unix). Returns True on success."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
                capture_output=True,
            )
            return result.returncode == 0
        else:
            dst.symlink_to(src, target_is_directory=True)
            return True
    except Exception as e:
        logger.debug(f"Could not create dir link {dst} -> {src}: {e}")
        return False


def _remove_venv_dir(path: Path) -> None:
    """Remove a venv directory, handling junctions on Windows."""
    if not path.exists() and not path.is_symlink():
        return
    if sys.platform == "win32" and path.is_junction():
        # Junctions must be unlinked, not rmtree'd (rmtree would delete the target).
        path.rmdir()
    elif path.is_symlink():
        path.unlink()
    else:
        shutil.rmtree(path)


def _build_venv(
    venv_dir: Path,
    coral_install_cmd: str,
    grader_config: GraderConfig,
    config_dir: Path,
) -> Path:
    """Create a venv at venv_dir, install coral, and run grader setup commands.

    Returns the path to the Python interpreter inside the venv.
    Raises RuntimeError on any failure.
    """
    python_path = (
        venv_dir / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else venv_dir / "bin" / "python"
    )

    venv_dir.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Creating grader venv at {venv_dir}")
    venv_cmd = ["uv", "venv", "--python", sys.executable, str(venv_dir)]
    result = subprocess.run(venv_cmd, capture_output=True, text=True, env=_clean_env())
    if result.returncode != 0:
        raise RuntimeError(
            f"`{' '.join(venv_cmd)}` failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    if not python_path.exists():
        raise RuntimeError(
            f"Expected Python interpreter at {python_path} after `uv venv`, but it does not exist"
        )

    extra_env = {
        "VIRTUAL_ENV": str(venv_dir),
        "PATH": f"{venv_dir / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
    }

    run_setup_commands([coral_install_cmd], cwd=config_dir, extra_env=extra_env)

    if grader_config.setup:
        run_setup_commands(grader_config.setup, cwd=config_dir, extra_env=extra_env)

    return python_path


def _build_cached_venv(
    cache_venv: Path,
    coral_install_cmd: str,
    grader_config: GraderConfig,
    config_dir: Path,
) -> bool:
    """Build the venv into the cache directory. Returns True on success."""
    tmp_dir = cache_venv.parent / f".tmp_{cache_venv.name}_{os.getpid()}"
    try:
        _build_venv(tmp_dir, coral_install_cmd, grader_config, config_dir)
        try:
            tmp_dir.rename(cache_venv)
        except Exception:
            # Another process may have won the race; clean up temp and use theirs.
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return True
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.debug(f"Failed to build cached venv: {e}")
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_grader_env(
    coral_dir: Path,
    grader_config: GraderConfig,
    config_dir: Path,
    *,
    rebuild: bool = False,
) -> Path:
    """Create the grader venv and run `grader_config.setup` commands in it.

    On first use for a given grader configuration, builds the venv and stores
    it in a shared cache. Subsequent calls with the same configuration reuse
    the cached venv via a directory junction (Windows) or symlink (Unix),
    avoiding redundant 300-500 MB installs across runs.

    Steps:
      1. Compute a cache key from the coral install command, grader setup
         commands, config directory, and Python version.
      2. If the cache already has a valid venv for this key, link
         `<run>/.coral/private/grader_venv/` → cache and return.
      3. Otherwise, build the venv into the cache (in a tmp dir, then rename),
         then link and return.
      4. If linking fails (permissions), fall back to building locally.

    Returns the path to the venv's Python interpreter.
    Raises RuntimeError on any failure with stdout/stderr in the message.
    """
    venv_dir = grader_venv_path(coral_dir)
    python_path = grader_python_path(coral_dir)

    if rebuild:
        _remove_venv_dir(venv_dir)

    # Fast path: venv already present (idempotent — covers both junction and real dir).
    if python_path.exists():
        return python_path

    # Attempt to compute a cache key.
    try:
        coral_install_cmd = _coral_install_command(_coral_install_origin())
        cache_key = _venv_cache_key(coral_install_cmd, grader_config, config_dir)
        cache_venv = _platform_cache_dir() / cache_key
    except Exception as e:
        logger.debug(f"Cannot compute venv cache key ({e}); building locally")
        coral_install_cmd = None
        cache_venv = None

    if cache_venv is not None:
        if rebuild and cache_venv.exists():
            shutil.rmtree(cache_venv, ignore_errors=True)

        # Cache hit: link into run dir and return.
        if _cached_python_path(cache_venv).exists():
            venv_dir.parent.mkdir(parents=True, exist_ok=True)
            if _make_dir_link(venv_dir, cache_venv):
                logger.info(f"Reusing cached grader venv ({cache_key[:8]}…)")
                return python_path
            logger.debug("Dir link failed; building locally despite cache hit")

        # Cache miss: build into cache, then link.
        assert coral_install_cmd is not None
        cache_venv.parent.mkdir(parents=True, exist_ok=True)
        if _build_cached_venv(cache_venv, coral_install_cmd, grader_config, config_dir):
            venv_dir.parent.mkdir(parents=True, exist_ok=True)
            if _make_dir_link(venv_dir, cache_venv):
                logger.info(f"Built and cached grader venv ({cache_key[:8]}…) at {cache_venv}")
                return python_path
            logger.debug("Dir link failed after cache build; falling back to local build")

    # Fallback: build the venv directly inside the run directory.
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    assert coral_install_cmd is not None or True  # may be None if origin lookup failed
    try:
        ci_cmd = coral_install_cmd or _coral_install_command(_coral_install_origin())
    except Exception as e:
        raise RuntimeError(f"Cannot determine coral install command: {e}") from e
    _build_venv(venv_dir, ci_cmd, grader_config, config_dir)
    return python_path
