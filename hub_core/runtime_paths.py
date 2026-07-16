import os
import tempfile

from hub_core.path_identity import canonical_path
from hub_core.runtime_boundary import (
    RuntimeBoundaryError,
    activate_runtime_root,
    runtime_project_id,
    safe_runtime_segment,
    validate_runtime_location,
)


def _repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _default_user_cache_dir():
    if os.name == "nt":
        return os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    if os.name == "posix" and os.uname().sysname == "Darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Caches")
    return os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")


def _abspath(value):
    raw = str(value)
    expanded = os.path.expanduser(raw)
    if expanded == raw and raw.startswith("~"):
        suffix = raw[1:].lstrip("/\\")
        expanded = os.path.join(tempfile.gettempdir(), suffix)
    return os.path.abspath(expanded)


def _usable_runtime_dir(path, *, project_root=None, config=None, durable_roots=()):
    try:
        return str(
            activate_runtime_root(
                _abspath(path),
                project_root=project_root,
                config=config,
                durable_roots=durable_roots,
            )
        )
    except RuntimeBoundaryError:
        return None


def _preview_temp_dir():
    for env_name in ("TMPDIR", "TEMP", "TMP"):
        value = os.environ.get(env_name)
        if value:
            return _abspath(value)
    if os.name == "nt":
        return _abspath(
            os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp")
        )
    return os.path.abspath(os.sep + "tmp")


def _preview_usable_runtime_dir(path):
    candidate = _abspath(path)
    if os.path.isdir(candidate):
        return candidate if os.access(candidate, os.W_OK | os.X_OK) else None
    if os.path.exists(candidate):
        return None

    ancestor = os.path.dirname(candidate) or os.curdir
    while ancestor and not os.path.exists(ancestor):
        parent = os.path.dirname(ancestor)
        if parent == ancestor:
            break
        ancestor = parent

    if os.path.isdir(ancestor) and os.access(ancestor, os.W_OK | os.X_OK):
        return candidate
    return None


def _repo_runtime_root_from_symlink():
    hub_logs_path = os.path.join(_repo_root(), "hub_logs")
    if os.path.islink(hub_logs_path):
        target = os.path.realpath(hub_logs_path)
        return os.path.dirname(target)
    return None


def runtime_root_env_override():
    # Server storage precedence is explicit and backward-compatible:
    # RESEARCH_HUB_RUNTIME_ROOT > RESEARCH_HUB_RUNTIME_HOME > GRAPH_HUB_RUNTIME_ROOT.
    return (
        os.environ.get("RESEARCH_HUB_RUNTIME_ROOT")
        or os.environ.get("RESEARCH_HUB_RUNTIME_HOME")
        or os.environ.get("GRAPH_HUB_RUNTIME_ROOT")
    )


def preview_runtime_root(*, project_root=None, config=None, durable_roots=()):
    """Return the preferred runtime root path without creating or probing directories."""
    override = runtime_root_env_override()
    candidates = []
    if override:
        candidates.append(override)
    repo_runtime_root = _repo_runtime_root_from_symlink()
    if repo_runtime_root:
        candidates.append(repo_runtime_root)
    candidates.append(os.path.join(_default_user_cache_dir(), "FigOps"))
    candidates.append(os.path.join(_preview_temp_dir(), "figops_runtime"))

    for candidate in candidates:
        usable = _preview_usable_runtime_dir(candidate)
        if usable:
            return str(
                validate_runtime_location(
                    usable,
                    project_root=project_root,
                    config=config,
                    durable_roots=durable_roots,
                )
            )

    return str(
        validate_runtime_location(
            _abspath(os.path.join(_preview_temp_dir(), "figops_runtime")),
            project_root=project_root,
            config=config,
            durable_roots=durable_roots,
        )
    )


def runtime_root_lookup_candidates():
    """Return runtime root candidates for metadata lookups without creating directories."""
    candidates = []
    override = runtime_root_env_override()
    if override:
        candidates.append(override)
    repo_runtime_root = _repo_runtime_root_from_symlink()
    if repo_runtime_root:
        candidates.append(repo_runtime_root)
    candidates.append(os.path.join(_default_user_cache_dir(), "FigOps"))
    candidates.append(os.path.join(_preview_temp_dir(), "figops_runtime"))
    try:
        candidates.append(os.path.join(tempfile.gettempdir(), "figops_runtime"))
    except OSError:
        pass

    deduped = []
    seen = set()
    for candidate in candidates:
        normalized = canonical_path(_abspath(candidate))
        identity = os.path.normcase(os.path.normpath(str(normalized)))
        if identity not in seen:
            deduped.append(str(normalized))
            seen.add(identity)
    return deduped


def resolve_runtime_root(*, project_root=None, config=None, durable_roots=()):
    override = runtime_root_env_override()
    effective_project_root = project_root or os.environ.get("PROJECT_ROOT")
    if override:
        # Launcher values are trusted policy inputs, not exemptions from boundary validation.
        return str(
            activate_runtime_root(
                _abspath(override),
                project_root=effective_project_root,
                config=config,
                durable_roots=durable_roots,
            )
        )
    candidates = []
    repo_runtime_root = _repo_runtime_root_from_symlink()
    if repo_runtime_root:
        candidates.append(repo_runtime_root)
    candidates.append(os.path.join(_default_user_cache_dir(), "FigOps"))
    candidates.append(os.path.join(tempfile.gettempdir(), "figops_runtime"))

    for candidate in candidates:
        usable = _usable_runtime_dir(
            candidate,
            project_root=effective_project_root,
            config=config,
            durable_roots=durable_roots,
        )
        if usable:
            return usable

    raise RuntimeBoundaryError("No valid writable external FigOps runtime root is available.")


def resolve_hub_logs_dir(*, project_root=None, config=None):
    return os.path.join(resolve_runtime_root(project_root=project_root, config=config), "logs")


def resolve_latest_publish_dir(engine_target: str = "hub_pipeline", job_id: str = "", *, project_root=None):
    normalized_target = safe_runtime_segment(engine_target, fallback="hub_pipeline")
    latest_dir = os.path.join(resolve_runtime_root(project_root=project_root), "_latest", normalized_target)
    if job_id:
        latest_dir = os.path.join(latest_dir, safe_runtime_segment(job_id, fallback="job"))
    return latest_dir


def resolve_execution_artifacts_dir(project_dir: str, engine_target: str = "hub_pipeline"):
    normalized_target = safe_runtime_segment(engine_target, fallback="hub_pipeline")
    root = resolve_runtime_root(project_root=project_dir)
    return os.path.join(root, "execution", runtime_project_id(project_dir), normalized_target)


def resolve_build_state_path(project_dir: str):
    root = resolve_runtime_root(project_root=project_dir)
    return os.path.join(root, "cache", "build_state", runtime_project_id(project_dir), ".build_state.json")


def resolve_diagnostics_dir(project_dir: str):
    root = resolve_runtime_root(project_root=project_dir)
    return os.path.join(root, "diagnostics", runtime_project_id(project_dir))


def resolve_failure_dir(project_dir: str):
    root = resolve_runtime_root(project_root=project_dir)
    return os.path.join(root, "failures", runtime_project_id(project_dir))


def resolve_preview_temp_dir():
    path = os.path.join(resolve_runtime_root(), "previews", "temp")
    os.makedirs(path, exist_ok=True)
    return path


def resolve_temp_dir(kind: str = "general", *, project_root=None, config=None):
    path = os.path.join(
        resolve_runtime_root(project_root=project_root, config=config),
        "temp",
        safe_runtime_segment(kind, fallback="general"),
    )
    os.makedirs(path, exist_ok=True)
    return path


def ensure_runtime_dirs(*paths):
    created = []
    for path in paths:
        if not path:
            continue
        os.makedirs(path, exist_ok=True)
        created.append(path)
    return created
