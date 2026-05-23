import ctypes
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .selfcheck import InitCheck


def _configure_windows_stdio() -> None:
    if sys.platform != "win32":
        return
    _set_windows_console_utf8()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _set_windows_console_utf8() -> None:
    kernel32 = getattr(ctypes, "windll", None)
    if kernel32 is None:
        return
    kernel32.kernel32.SetConsoleOutputCP(65001)
    kernel32.kernel32.SetConsoleCP(65001)


_configure_windows_stdio()
console = Console(legacy_windows=False)


def print_banner() -> None:
    console.print(Panel.fit("[bold cyan]LCP[/bold cyan]\nLark Claude Profile Manager", border_style="cyan"))


def print_checks(checks: list[InitCheck]) -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("status", width=4)
    table.add_column("name", style="bold")
    table.add_column("value")
    for check in checks:
        if check.status == "ok":
            marker = "[green]✓[/green]"
        elif check.status == "warn":
            marker = "[yellow]![/yellow]"
        else:
            marker = "[red]✗[/red]"
        style = "green" if check.status == "ok" else "yellow" if check.status == "warn" else "red"
        table.add_row(marker, check.name, f"[{style}]{check.value}[/{style}]")
    console.print(table)
