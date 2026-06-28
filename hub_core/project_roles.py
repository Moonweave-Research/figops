"""Project role and lifecycle helpers for project configuration."""

from __future__ import annotations

ALLOWED_PROJECT_ROLES = {"master", "module"}
ALLOWED_PROJECT_STATUSES = {"active", "legacy"}
ALLOWED_FOLDER_ROLES = {
    "module",
    "raw_reservoir",
    "reference",
    "theory",
    "exploratory",
    "docs",
    "support",
    "archive",
}
DEFAULT_PROJECT_ROLE = "module"
DEFAULT_PROJECT_STATUS = "active"


def project_role(config):
    project = config.get("project") if isinstance(config, dict) else {}
    if not isinstance(project, dict):
        return DEFAULT_PROJECT_ROLE
    role = project.get("role", DEFAULT_PROJECT_ROLE)
    if not isinstance(role, str):
        return DEFAULT_PROJECT_ROLE
    role = role.strip().lower()
    return role if role else DEFAULT_PROJECT_ROLE


def project_status(config):
    project = config.get("project") if isinstance(config, dict) else {}
    if not isinstance(project, dict):
        return DEFAULT_PROJECT_STATUS
    status = project.get("status", DEFAULT_PROJECT_STATUS)
    if not isinstance(status, str):
        return DEFAULT_PROJECT_STATUS
    status = status.strip().lower()
    return status if status else DEFAULT_PROJECT_STATUS


def project_modules(config):
    modules = config.get("modules", []) if isinstance(config, dict) else []
    if not isinstance(modules, list):
        return []
    return [str(module).strip() for module in modules if isinstance(module, str) and module.strip()]


def folder_role_map(config):
    folder_roles = config.get("folder_roles", {}) if isinstance(config, dict) else {}
    if not isinstance(folder_roles, dict):
        return {}
    result = {}
    for raw_path, raw_role in folder_roles.items():
        if isinstance(raw_path, str) and isinstance(raw_role, str):
            path = raw_path.strip().strip("/\\")
            role = raw_role.strip().lower()
            if path and role:
                result[path.replace("\\", "/")] = role
    return result


def master_execution_error(config):
    modules = project_modules(config)
    module_list = ", ".join(modules) if modules else "none declared"
    return f"This is a master project root, not an execution module — enter one of its modules: [{module_list}]"


def normalize_project_defaults(config):
    if not isinstance(config, dict):
        return config
    project = config.get("project")
    if isinstance(project, dict):
        if "role" not in project:
            project["role"] = DEFAULT_PROJECT_ROLE
        elif isinstance(project.get("role"), str):
            project["role"] = project["role"].strip().lower()
        if "status" not in project:
            project["status"] = DEFAULT_PROJECT_STATUS
        elif isinstance(project.get("status"), str):
            project["status"] = project["status"].strip().lower()
    return config
