"""Small, supported Python entry points for FigOps project scripts.

Project scripts should import public helpers from this module instead of
relying on the repository layout or on the MCP implementation package.
"""

from themes.journal_theme import save_journal_fig

__all__ = ["save_journal_fig"]
