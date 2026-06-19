import sys

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    from rich.table import Table
    HAS_RICH = True
    console = Console(stderr=True)
except ImportError:
    HAS_RICH = False
    console = None

def ui_print(message, style=None):
    if HAS_RICH:
        console.print(message, style=style)
    else:
        # Simple fallback for standard print
        # Remove rich-style tags if present
        import re
        clean_msg = re.sub(r'\[/?[a-z #0-9]+\]', '', str(message))
        print(clean_msg, file=sys.stderr)

def ui_panel(message, title=None, subtitle=None, style="blue"):
    if HAS_RICH:
        ui_print(Panel(message, title=title, subtitle=subtitle, border_style=style))
    else:
        print(f"\n{'='*10} {title if title else ''} {'='*10}", file=sys.stderr)
        print(message, file=sys.stderr)
        print('='*30, file=sys.stderr)

def ui_table(title, columns, rows):
    if HAS_RICH:
        table = Table(title=title, show_header=True, header_style="bold magenta")
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*row)
        console.print(table)
    else:
        print(f"\n--- {title} ---", file=sys.stderr)
        header = " | ".join(columns)
        print(header, file=sys.stderr)
        print("-" * len(header), file=sys.stderr)
        for row in rows:
            print(" | ".join(map(str, row)), file=sys.stderr)
        print("-" * len(header), file=sys.stderr)

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
