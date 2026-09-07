#!/usr/bin/env python3
"""
mediafetch.tui - Alternate-Buffer Full-Screen TUI Dashboard, Widgets, and Signal Management
"""

import sys
import os
import time
import select
import signal
import threading
from pathlib import Path

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich import box

try:
    from .utils import get_console, PROFILES
    from .downloader import DashboardState
except ImportError:
    from utils import get_console, PROFILES
    from downloader import DashboardState


class KeyboardListener:
    """Non-blocking background stdin listener for hotkeys ('q' to abort, 'c' to clear completed)."""
    def __init__(self, shutdown_event: threading.Event, state: DashboardState):
        self.shutdown_event = shutdown_event
        self.state = state
        self.running = False
        self.thread = None
        self.old_settings = None

    def start(self):
        if not sys.stdin.isatty():
            return
        try:
            import termios
            import tty
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        except Exception:
            pass

    def _run(self):
        while self.running and not self.shutdown_event.is_set():
            try:
                r, _, _ = select.select([sys.stdin], [], [], 0.15)
                if r:
                    ch = sys.stdin.read(1)
                    if ch in ('q', 'Q', '\x03'):  # 'q' or Ctrl+C
                        self.shutdown_event.set()
                        break
                    elif ch in ('c', 'C'):
                        with self.state.lock:
                            setattr(self.state, 'hide_completed', not getattr(self.state, 'hide_completed', False))
            except Exception:
                break

    def stop(self):
        self.running = False
        if self.old_settings and sys.stdin.isatty():
            try:
                import termios
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
            except Exception:
                pass


def render_dashboard(state: DashboardState, width: int = 100, height: int = 24) -> Layout:
    """Renders the pristine full-screen alternate-buffer dashboard."""
    with state.lock:
        items = list(state.items)
        active_idx = state.active_idx
        completed = state.completed_count
        total = len(items)
        prof_info = PROFILES.get(state.profile_name, {})
        is_music = prof_info.get("type") == "music"
        format_desc = prof_info.get("format_desc", state.profile_name.upper())

        # Aggregate download speed
        total_speed = sum(it.speed for it in items if it.status == "downloading")
        speed_str = f"{total_speed / 1048576:.1f} MB/s" if total_speed > 0 else "Idle"

        # Elapsed calculation
        elapsed_sec = int(time.time() - state.start_time)
        elapsed_str = f"{elapsed_sec // 60:02d}:{elapsed_sec % 60:02d}"

        # Active item for inspector
        inspect_item = items[active_idx] if 0 <= active_idx < len(items) else (items[0] if items else None)

    # 1. Root Layout Structure
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="gauge", size=3),
        Layout(name="footer", size=3)
    )
    layout["main"].split_row(
        Layout(name="queue", ratio=3),
        Layout(name="details", ratio=2)
    )

    # 2. Header Panel
    target_short = str(state.target_dir).replace(str(Path.home()), "~")
    unit_label = "Track" if is_music else "Video"
    queue_count_str = f"{total} {unit_label}{'s' if total != 1 else ''}"
    header_content = (
        f"  Mode: [bold cyan]{state.profile_name.upper()}[/] [dim]({format_desc})[/]   │   "
        f"Dest: [white]{target_short}[/]   │   "
        f"Queue: [bold white]{queue_count_str}[/]   │   "
        f"ARIA2: [bold green]8x[/]"
    )
    layout["header"].update(Panel(
        header_content,
        title="[bold cyan]📥 Media Fetcher (mf)[/]",
        title_align="left",
        box=box.ROUNDED,
        border_style="cyan"
    ))

    # 3. Queue Panel (Dynamically adapt to terminal height)
    max_queue_rows = min(18, max(5, height - 14))
    if getattr(state, 'hide_completed', False):
        display_items = [it for it in items if it.status != "done"]
    else:
        display_items = items

    if len(display_items) <= max_queue_rows:
        start_idx = 0
        end_idx = len(display_items)
    else:
        half = max_queue_rows // 2
        start_idx = max(0, min(active_idx - half, len(display_items) - max_queue_rows))
        end_idx = min(len(display_items), start_idx + max_queue_rows)

    visible_items = display_items[start_idx:end_idx]

    q_table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    q_table.add_column("num", width=5, style="dim")
    q_table.add_column("name", ratio=3, no_wrap=True)
    q_table.add_column("status", ratio=2, justify="right", no_wrap=True)

    for it in visible_items:
        idx_str = f"[{it.idx+1:02d}]"
        clean_name = it.title[:38]

        if it.status == "done":
            name_cell = f"[green]✓ {clean_name}[/]"
            if is_music and state.phase == "Lyrics Tagging" and it.lyrics_status:
                status_cell = it.lyrics_status
            else:
                status_cell = f"[dim]{it.final_size_str or 'Done'}[/] [green]✓[/]"
        elif it.status == "downloading":
            name_cell = f"[bold cyan]⠋ {clean_name}[/]"
            speed_txt = f"{it.speed/1048576:.1f} M/s" if it.speed else ""
            status_cell = f"[cyan]{it.percent:>3.0f}% {speed_txt}[/]"
        elif it.status == "processing":
            name_cell = f"[magenta]⚡ {clean_name}[/]"
            status_cell = f"[magenta]{it.stage_text}[/]"
        elif it.status == "error":
            name_cell = f"[red]✗ {clean_name}[/]"
            if it.stage_text in ("Age Restricted", "Expired Cookies"):
                status_cell = f"[bold yellow]{it.stage_text}[/]"
            else:
                status_cell = f"[red]{it.stage_text or 'Error'}[/]"
        else:
            name_cell = f"[dim]· {clean_name}[/]"
            status_cell = "[dim]Queued[/]"

        q_table.add_row(idx_str, name_cell, status_cell)

    window_label = f"Showing {start_idx+1}-{end_idx} of {len(display_items)}" if len(display_items) > max_queue_rows else f"{len(display_items)} {unit_label}{'s' if len(display_items) != 1 else ''}"
    layout["queue"].update(Panel(
        q_table,
        title="[bold cyan]📋 Media Queue[/]",
        title_align="left",
        subtitle=f"[dim]{window_label}[/]",
        subtitle_align="left",
        box=box.ROUNDED,
        border_style="blue"
    ))

    # 4. Inspector Panel (Track Inspector for Music, Video Inspector for Video)
    d_table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    d_table.add_column("label", width=12, style="bold cyan", no_wrap=True)
    d_table.add_column("value", ratio=1, no_wrap=True)

    inspector_title = "[bold cyan]ℹ️ Track Inspector[/]" if is_music else "[bold cyan]ℹ️ Video Inspector[/]"

    if inspect_item:
        if inspect_item.status == "error" and inspect_item.stage_text in ("Age Restricted", "Expired Cookies"):
            stage_style = "[bold yellow]"
        elif inspect_item.status == "processing":
            stage_style = "[magenta]"
        else:
            stage_style = "[cyan]"

        if is_music:
            d_table.add_row("Track:", f"[bold white]{inspect_item.title[:26]}[/]")
            d_table.add_row("Artist:", f"{inspect_item.artist[:26] or '[dim]Unknown[/]'}")
            d_table.add_row("Album:", f"{inspect_item.album[:26] or '[dim]Unknown[/]'}")
            d_table.add_row("Format:", f"[green]{format_desc}[/]")
            cover_desc = "1:1 Square Cropped" if "music" in state.profile_name or "flac" in state.profile_name else "Embedded Art"
            d_table.add_row("Cover:", f"[dim]{cover_desc}[/]")
            lyrics_text = inspect_item.lyrics_status or ("[dim]Pending[/]" if state.phase != "Complete" else "[dim]None[/]")
            d_table.add_row("Lyrics:", lyrics_text)
            d_table.add_row("Stage:", f"{stage_style}{inspect_item.stage_text}[/]")

            if inspect_item.status == "downloading":
                d_table.add_row("Current DL:", f"[cyan]{inspect_item.percent:.0f}% ({inspect_item.speed/1048576:.1f} MB/s)[/]")
            elif inspect_item.status == "done":
                d_table.add_row("Current DL:", f"[green]Done ({inspect_item.final_size_str})[/]")
            else:
                d_table.add_row("Current DL:", f"[dim]{inspect_item.stage_text}[/]")
        else:
            # Video mode: Clean video-specific attributes
            d_table.add_row("Title:", f"[bold white]{inspect_item.title[:26]}[/]")
            d_table.add_row("Format:", f"[green]{format_desc}[/]")
            if state.profile_name == "shorts":
                d_table.add_row("Type:", "[dim]Vertical (9:16)[/]")
            else:
                d_table.add_row("Subtitles:", "[dim]English (Auto-Embed)[/]")
            d_table.add_row("Thumbnail:", "[dim]Embedded PNG[/]")
            d_table.add_row("Stage:", f"{stage_style}{inspect_item.stage_text}[/]")

            if inspect_item.status == "downloading":
                dl_str = f"{inspect_item.percent:.0f}%"
                if inspect_item.speed > 0:
                    dl_str += f" ({inspect_item.speed/1048576:.1f} MB/s)"
                d_table.add_row("Current DL:", f"[cyan]{dl_str}[/]")
            elif inspect_item.status == "done":
                d_table.add_row("Current DL:", f"[green]Done ({inspect_item.final_size_str})[/]")
            else:
                d_table.add_row("Current DL:", f"[dim]{inspect_item.stage_text}[/]")
    else:
        d_table.add_row("Status:", "[dim]Ready[/]")

    layout["details"].update(Panel(
        d_table,
        title=inspector_title,
        title_align="left",
        subtitle="[dim]Details[/]",
        subtitle_align="left",
        box=box.ROUNDED,
        border_style="magenta"
    ))

    # 5. Full-Width Progress Gauge Panel
    pct, gauge_title, _ = state.get_progress_info()
    inner_w = max(10, width - 4)
    filled = int(max(0.0, min(100.0, pct)) / 100.0 * inner_w)
    f_chars = "█" * filled
    u_chars = "░" * (inner_w - filled)
    bar_markup = f"[bold cyan]{f_chars}[dim cyan]{u_chars}[/]"

    layout["gauge"].update(Panel(
        bar_markup,
        title=f"[bold cyan]{gauge_title}[/]",
        title_align="left",
        box=box.ROUNDED,
        border_style="cyan"
    ))

    # 6. Status & Metrics Footer Panel
    if is_music:
        lyrics_txt = f"[bold green]{state.synced_lyrics_count} Synced[/], [dim yellow]{state.skipped_lyrics_count} Skipped[/]"
        footer_content = (
            f"  🚀 Speed: [bold green]{speed_str}[/]   │   "
            f"⏱️ Elapsed: [bold white]{elapsed_str}[/]   │   "
            f"🎵 Lyrics: {lyrics_txt}   │   "
            f"Phase: [bold cyan]{state.phase}[/]"
        )
    else:
        footer_content = (
            f"  🚀 Speed: [bold green]{speed_str}[/]   │   "
            f"⏱️ Elapsed: [bold white]{elapsed_str}[/]   │   "
            f"🎬 Preset: [bold cyan]{state.profile_name.upper()}[/]   │   "
            f"Phase: [bold cyan]{state.phase}[/]"
        )

    layout["footer"].update(Panel(
        footer_content,
        title="[bold cyan]📊 Status & Metrics[/]",
        title_align="left",
        subtitle="[bold cyan]\\[q][/] [dim]Abort / Exit[/]   [bold cyan]\\[c][/] [dim]Clear Completed[/]",
        subtitle_align="left",
        box=box.ROUNDED,
        border_style="dim"
    ))

    return layout


def render_final_summary_panel(state: DashboardState, console):
    """Renders the finalized, pristine summary card printed to standard terminal."""
    from rich.panel import Panel

    prof_info = PROFILES.get(state.profile_name, {})
    is_music = prof_info.get("type") == "music"
    unit_label = "Track" if is_music else "Video"
    title_header = "Track Title" if is_music else "Video Title"
    status_header = "Status / Lyrics" if is_music else "Status"
    summary_title = "📥 Download & Tagging Complete" if is_music else "📥 Download Complete"

    table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE_HEAVY, expand=True)
    table.add_column("#", style="dim", width=4)
    table.add_column(title_header, style="bold white", min_width=32)
    table.add_column("Size", style="cyan", width=12, justify="right")
    table.add_column(status_header, style="green", width=22 if is_music else 19, justify="right")

    has_age_restricted = False
    has_expired_cookies = False

    for idx, item in enumerate(state.items, 1):
        clean_name = item.title[:45]
        if item.status == "done":
            status_disp = item.lyrics_status or "[green]✓ Saved[/]"
        elif item.stage_text == "Age Restricted":
            status_disp = "[bold yellow]✗ Age-Restricted[/]"
            has_age_restricted = True
        elif item.stage_text == "Expired Cookies":
            status_disp = "[bold yellow]✗ Expired Cookies[/]"
            has_expired_cookies = True
        else:
            status_disp = "[red]✗ Failed[/]"

        table.add_row(f"{idx:02d}", clean_name, item.final_size_str or "-", status_disp)

    target_short = str(state.target_dir).replace(str(Path.home()), "~")
    count_str = f"{len(state.items)} {unit_label}{'s' if len(state.items) != 1 else ''}"
    summary_panel = Panel(
        table,
        title=f"[bold cyan]{summary_title} • {count_str} ➔ {target_short}[/]",
        box=box.ROUNDED,
        border_style="cyan"
    )
    console.print()
    console.print(summary_panel)

    if has_age_restricted or has_expired_cookies:
        tip_lines = []
        if has_age_restricted:
            tip_lines.append("[yellow]• One or more tracks are age-restricted and require YouTube sign-in authentication.[/]")
        if has_expired_cookies:
            tip_lines.append("[yellow]• The provided cookies in cookies.txt are expired or have been rotated by YouTube.[/]")
        tip_lines.append("[dim]• Place fresh Netscape-formatted cookies at: [cyan]~/.config/mediafetch/cookies.txt[/][/]")
        tip_lines.append("[dim]  or run mediafetch with: [cyan]mf --cookies <path/to/cookies.txt> [URL][/][/]")

        console.print(Panel(
            "\n".join(tip_lines),
            title="[bold yellow]⚠️  Authentication Notice[/]",
            box=box.ROUNDED,
            border_style="yellow"
        ))
    console.print()
