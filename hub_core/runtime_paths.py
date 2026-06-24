import os
import tempfile


def _repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _default_user_cache_dir():
    if os.name == "nt":
        return os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    if os.name == "posix" and os.uname().sysname == "Darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Caches")
    return os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")


def _abspath(value):
    return os.path.abspath(os.path.expanduser(str(value)))


def _usable_runtime_dir(path):
    candidate = _abspath(path)
    try:
        os.makedirs(candidate, exist_ok=True)
    except OSError:
        return None
    if os.access(candidate, os.W_OK | os.X_OK):
        return candidate
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


def preview_runtime_root():
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
            return usable

    return _abspath(os.path.join(_preview_temp_dir(), "figops_runtime"))


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
        normalized = _abspath(candidate)
        if normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped


def resolve_runtime_root():
    override = runtime_root_env_override()
    candidates = []
    if override:
        candidates.append(override)
    repo_runtime_root = _repo_runtime_root_from_symlink()
    if repo_runtime_root:
        candidates.append(repo_runtime_root)
    candidates.append(os.path.join(_default_user_cache_dir(), "FigOps"))
    candidates.append(os.path.join(tempfile.gettempdir(), "figops_runtime"))

    for candidate in candidates:
        usable = _usable_runtime_dir(candidate)
        if usable:
            return usable

    return os.path.abspath(os.path.join(tempfile.gettempdir(), "figops_runtime"))


def resolve_hub_logs_dir():
    return os.path.join(resolve_runtime_root(), "hub_logs")


def resolve_latest_publish_dir(engine_target: str = "hub_pipeline", job_id: str = ""):
    normalized_target = str(engine_target or "hub_pipeline").strip() or "hub_pipeline"
    latest_dir = os.path.join(resolve_runtime_root(), "_latest", normalized_target)
    if job_id:
        latest_dir = os.path.join(latest_dir, str(job_id))
    return latest_dir


def resolve_execution_artifacts_dir(project_dir: str, engine_target: str = "hub_pipeline"):
    normalized_target = str(engine_target or "hub_pipeline").strip() or "hub_pipeline"
    return os.path.join(_abspath(project_dir), "results", "_execution", normalized_target)


def ensure_runtime_dirs(*paths):
    created = []
    for path in paths:
        if not path:
            continue
        os.makedirs(path, exist_ok=True)
        created.append(path)
    return created
