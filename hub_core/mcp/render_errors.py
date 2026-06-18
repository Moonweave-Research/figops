from __future__ import annotations


class ProjectRenderExportError(RuntimeError):
    """Project render setup/export failed before a plotting script completed successfully."""

    def __init__(self, message: str, *, script_output: list[str] | None = None) -> None:
        super().__init__(message)
        self.script_output = script_output or []


class ProjectRenderScriptError(RuntimeError):
    """The selected project plotting script ran and exited unsuccessfully."""

    def __init__(self, message: str, *, returncode: int | None, script_output: list[str] | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.script_output = script_output or []
