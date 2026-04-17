import sys
import os

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import print as rprint
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None

def ui_print(message, style=None):
    if HAS_RICH:
        rprint(message)
    else:
        # Simple fallback for standard print
        # Remove rich-style tags if present
        import re
        clean_msg = re.sub(r'\[/?[a-z #0-9]+\]', '', str(message))
        print(clean_msg)

def ui_panel(message, title=None, subtitle=None, style="blue"):
    if HAS_RICH:
        ui_print(Panel(message, title=title, subtitle=subtitle, border_style=style))
    else:
        print(f"\n{'='*10} {title if title else ''} {'='*10}")
        print(message)
        print('='*30)

def ui_table(title, columns, rows):
    if HAS_RICH:
        table = Table(title=title, show_header=True, header_style="bold magenta")
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*row)
        console.print(table)
    else:
        print(f"\n--- {title} ---")
        header = " | ".join(columns)
        print(header)
        print("-" * len(header))
        for row in rows:
            print(" | ".join(map(str, row)))
        print("-" * len(header))

def ui_prompt(message, default=None):
    if HAS_RICH:
        return Prompt.ask(message, default=default)
    else:
        prompt_msg = f"{message} [{default}]: " if default else f"{message}: "
        res = input(prompt_msg).strip()
        return res if res else default

def ui_confirm(message, default=True):
    if HAS_RICH:
        return Confirm.ask(message, default=default)
    else:
        prompt_msg = f"{message} ({'Y/n' if default else 'y/N'}): "
        res = input(prompt_msg).strip().lower()
        if not res:
            return default
        return res.startswith('y')
