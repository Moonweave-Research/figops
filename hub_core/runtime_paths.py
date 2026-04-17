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


def _repo_runtime_root_from_symlink():
    hub_logs_path = os.path.join(_repo_root(), "hub_logs")
    if os.path.islink(hub_logs_path):
        target = os.path.realpath(hub_logs_path)
        return os.path.dirname(target)
    return None


def resolve_runtime_root():
    override = os.environ.get("RESEARCH_HUB_RUNTIME_ROOT") or os.environ.get("RESEARCH_HUB_RUNTIME_HOME")
    candidates = []
    if override:
        candidates.append(override)
    repo_runtime_root = _repo_runtime_root_from_symlink()
    if repo_runtime_root:
        candidates.append(repo_runtime_root)
    candidates.append(os.path.join(_default_user_cache_dir(), "Graph_making_hub"))
    candidates.append(os.path.join(tempfile.gettempdir(), "graph_making_hub_runtime"))

    for candidate in candidates:
        usable = _usable_runtime_dir(candidate)
        if usable:
            return usable

    return os.path.abspath(os.path.join(tempfile.gettempdir(), "graph_making_hub_runtime"))


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


def resolve_dvc_home():
    override = os.environ.get("RESEARCH_HUB_DVC_HOME")
    if override:
        return _abspath(override)
    return os.path.join(resolve_runtime_root(), "dvc_home")


def ensure_runtime_dirs(*paths):
    created = []
    for path in paths:
        if not path:
            continue
        os.makedirs(path, exist_ok=True)
        created.append(path)
    return created


def fallback_temp_dvc_home():
    base = os.path.join(tempfile.gettempdir(), "graph_making_hub_dvc_home")
    return os.path.abspath(base)
