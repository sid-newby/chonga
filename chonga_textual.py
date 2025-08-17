#!/usr/bin/env python3
"""
Chonga Textual TUI

Menu-driven UI for converting media to WebM (VP9) with quality-first presets.
Works on macOS (Apple Silicon) and other platforms with ffmpeg installed.
"""

import asyncio
import os
import platform
import shlex
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    Switch,
    ProgressBar,
    Log,
)


# ------------------------------ Helpers ------------------------------


def format_bytes(num_bytes: float) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(num_bytes)
    unit_idx = 0
    while size >= 1024 and unit_idx < len(units) - 1:
        size /= 1024
        unit_idx += 1
    return f"{size:.1f} {units[unit_idx]}"


def parse_time_to_seconds(time_str: str) -> Optional[float]:
    try:
        if not time_str or time_str == "N/A":
            return None
        if "." in time_str:
            hms_part, fractional_part = time_str.split(".", 1)
        else:
            hms_part, fractional_part = time_str, None
        hours_str, minutes_str, seconds_str = hms_part.split(":")
        total_seconds: float = (
            int(hours_str) * 3600 + int(minutes_str) * 60 + int(seconds_str)
        )
        if fractional_part and fractional_part.isdigit():
            total_seconds += int(fractional_part) / (10 ** len(fractional_part))
        return total_seconds
    except Exception:
        return None


def parse_bitrate_to_bps(bitrate_str: str) -> Optional[int]:
    if not bitrate_str:
        return None
    s = bitrate_str.strip().lower()
    try:
        if s.endswith("k"):
            return int(float(s[:-1]) * 1_000)
        if s.endswith("m"):
            return int(float(s[:-1]) * 1_000_000)
        return int(float(s))
    except Exception:
        return None


def ffprobe_duration(path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return float(result.stdout.strip())


def ffprobe_wh(path: str) -> Optional[Tuple[int, int]]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0:s=x",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        line = result.stdout.strip()
        if "x" in line:
            w_str, h_str = line.split("x", 1)
            return int(w_str), int(h_str)
    except Exception:
        return None
    return None


def choose_vp9_tiling(width: Optional[int], height: Optional[int]) -> Tuple[int, int]:
    if width is None or height is None:
        return 1, 0
    if width > 3840:
        tile_cols = 4
    elif width > 1920:
        tile_cols = 3
    elif width > 1280:
        tile_cols = 2
    elif width > 640:
        tile_cols = 1
    else:
        tile_cols = 0
    tile_rows = 1 if height and height > 1440 else 0
    return tile_cols, tile_rows


# ------------------------------ UI Model ------------------------------


@dataclass
class Preset:
    label: str
    crf: int
    speed: int
    deadline: str


PRESETS: list[Preset] = [
    Preset("Quality First (CRF 28, speed 0, best)", crf=28, speed=0, deadline="best"),
    Preset("Balanced (CRF 30, speed 1, good)", crf=30, speed=1, deadline="good"),
    Preset("Smaller (CRF 32, speed 2, good)", crf=32, speed=2, deadline="good"),
    Preset("Speedy (CRF 30, speed 3, realtime)", crf=30, speed=3, deadline="realtime"),
]


class ConfigPanel(Static):
    """Left-side control panel."""

    def compose(self) -> ComposeResult:
        yield Label("CHONGA // ANARCHY MODE", id="title")
        yield Input(placeholder="Input file (mp4/mov)", id="in_path")
        yield Input(placeholder="Output file (.webm)", id="out_path")

        yield Label("Preset")
        yield Select(
            options=[(p.label, idx) for idx, p in enumerate(PRESETS)],
            value=1,
            id="preset",
        )

        yield Label("Mode")
        yield Select(
            options=[("Quality (CRF)", "crf"), ("Bitrate (2-pass)", "bitrate")],
            value="crf",
            id="mode",
        )

        yield Label("CRF (18-36 typical) or Bitrate (e.g. 1M, 800k)")
        yield Input(value="30", id="crf_or_bitrate")

        yield Label("Threads (0=auto)")
        yield Input(value="0", id="threads")

        yield Horizontal(
            Label("HW Decode"),
            Switch(value=True, id="hwdec"),
            classes="row",
        )

        yield Horizontal(
            Button("Start", id="start", variant="success"),
            Button("Stop", id="stop", variant="warning"),
            classes="row",
        )


class ProgressPanel(Static):
    """Right-side progress panel with log."""

    progress_value: reactive[float] = reactive(0.0)
    status_text: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Label("Progress")
        yield ProgressBar(total=100, id="bar")
        yield Label("", id="status")
        yield Log(id="log", highlight=True)

    def on_mount(self) -> None:
        bar = self.query_one("#bar", ProgressBar)
        bar.update(progress=0)

    def set_progress(self, percent: float, status: str = "") -> None:
        bar = self.query_one("#bar", ProgressBar)
        bar.update(progress=max(0, min(100, percent)))
        if status:
            self.query_one("#status", Label).update(status)

    def log(self, message: str) -> None:
        log = self.query_one("#log", Log)
        log.write(message)


class ChongaApp(App):
    CSS = """
    #title { text-style: bold; color: magenta; }
    .row { height: auto; content-align: center middle; }
    #bar { width: 100%; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("s", "start", "Start"),
    ]

    process: Optional[asyncio.subprocess.Process] = None
    duration_seconds: float = 0.0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="left"):
                yield ConfigPanel(id="config")
            with Vertical(id="right"):
                yield ProgressPanel(id="progress")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            await self.action_start()
        elif event.button.id == "stop":
            self.call_from_thread(self.stop_process)

    async def action_start(self) -> None:
        if self.process and self.process.returncode is None:
            return
        config = self.query_one("#config", ConfigPanel)
        progress = self.query_one("#progress", ProgressPanel)

        in_path = config.query_one("#in_path", Input).value.strip()
        out_path = config.query_one("#out_path", Input).value.strip()
        mode = config.query_one("#mode", Select).value
        preset_idx = int(config.query_one("#preset", Select).value)
        preset = PRESETS[preset_idx]
        crf_or_bitrate = config.query_one("#crf_or_bitrate", Input).value.strip()
        threads_str = config.query_one("#threads", Input).value.strip()
        hwdec = config.query_one("#hwdec", Switch).value

        if not in_path:
            progress.log("[red]Please provide an input file[/red]")
            return
        if not os.path.exists(in_path):
            progress.log(f"[red]Input not found:[/red] {in_path}")
            return
        if not out_path:
            root, _ = os.path.splitext(in_path)
            out_path = root + ".webm"
            config.query_one("#out_path", Input).value = out_path

        # Mode parsing
        bitrate: Optional[str] = None
        crf: int = preset.crf
        speed: int = preset.speed
        deadline: str = preset.deadline
        if mode == "crf":
            try:
                crf = int(crf_or_bitrate or crf)
            except Exception:
                pass
        else:
            bitrate = crf_or_bitrate or "1M"

        try:
            self.duration_seconds = ffprobe_duration(in_path)
        except Exception as exc:
            progress.log(f"[red]Could not read duration:[/red] {exc}")
            return

        dims = ffprobe_wh(in_path)
        width, height = (dims if dims else (None, None))
        tile_cols, tile_rows = choose_vp9_tiling(width, height)

        try:
            threads = int(threads_str)
        except Exception:
            threads = 0
        if threads <= 0:
            threads = os.cpu_count() or 4

        # Advisory for bitrate size
        if bitrate:
            bps = parse_bitrate_to_bps(bitrate)
            if bps:
                est_bytes = (bps / 8.0) * self.duration_seconds
                try:
                    src_bytes = os.path.getsize(in_path)
                    if est_bytes > src_bytes * 1.05:
                        progress.log(
                            f"[yellow]Note:[/yellow] Target bitrate implies ~{format_bytes(est_bytes)} output; may exceed source."
                        )
                except Exception:
                    pass

        progress.set_progress(0, status="Queued…")
        await self.encode_with_progress(
            in_path=in_path,
            out_path=out_path,
            bitrate=bitrate,
            crf=crf,
            speed=speed,
            deadline=deadline,
            threads=threads,
            tile_columns=tile_cols,
            tile_rows=tile_rows,
            hwdec=hwdec,
            two_pass=(bitrate is not None),
        )

    def stop_process(self) -> None:
        if self.process and self.process.returncode is None:
            try:
                self.process.kill()
            except Exception:
                pass

    async def encode_with_progress(
        self,
        *,
        in_path: str,
        out_path: str,
        bitrate: Optional[str],
        crf: int,
        speed: int,
        deadline: str,
        threads: int,
        tile_columns: int,
        tile_rows: int,
        hwdec: bool,
        two_pass: bool,
    ) -> None:
        progress = self.query_one("#progress", ProgressPanel)

        def build_cmd(pass_num: Optional[int] = None, passlog: Optional[str] = None, to_null: bool = False) -> list[str]:
            cmd: list[str] = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
            if hwdec and platform.system() == "Darwin":
                cmd += ["-hwaccel", "videotoolbox"]
            cmd += [
                "-i",
                in_path,
                "-an",
                "-c:v",
                "libvpx-vp9",
                "-pix_fmt",
                "yuv420p",
                "-row-mt",
                "1",
                "-tile-columns",
                str(tile_columns),
                "-tile-rows",
                str(tile_rows),
                "-threads",
                str(threads),
                "-aq-mode",
                "1",
                "-auto-alt-ref",
                "1",
                "-lag-in-frames",
                "25",
                "-cpu-used",
                str(speed),
                "-deadline",
                deadline,
            ]
            if bitrate:
                cmd += ["-b:v", bitrate]
            else:
                cmd += ["-crf", str(crf), "-b:v", "0"]
            if pass_num is not None and passlog is not None:
                cmd += ["-pass", str(pass_num), "-passlogfile", passlog]
            cmd += ["-progress", "pipe:1", "-nostats"]
            if to_null:
                cmd += ["-f", "null", "/dev/null"]
            else:
                cmd += [out_path]
            return cmd

        async def run_cmd(cmd: list[str]) -> int:
            self.log.debug("Running: %s", shlex.join(cmd))
            self.process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            assert self.process.stdout is not None
            while True:
                line_bytes = await self.process.stdout.readline()
                if not line_bytes:
                    break
                try:
                    s = line_bytes.decode("utf-8", errors="ignore").strip()
                except Exception:
                    s = ""
                if s.startswith("out_time_ms="):
                    value = s.split("=", 1)[1].strip()
                    if value.isdigit():
                        seconds = int(value) / 1_000_000
                        pct = (seconds / max(1.0, self.duration_seconds)) * 100.0
                        progress.set_progress(pct, status=f"{seconds:.1f}s / {self.duration_seconds:.1f}s")
                elif s.startswith("out_time="):
                    seconds_opt = parse_time_to_seconds(s.split("=", 1)[1].strip())
                    if seconds_opt is not None:
                        pct = (seconds_opt / max(1.0, self.duration_seconds)) * 100.0
                        progress.set_progress(pct, status=f"{seconds_opt:.1f}s / {self.duration_seconds:.1f}s")
                elif s.startswith("progress="):
                    progress.log(s)
            await self.process.wait()
            return self.process.returncode or 0

        return_code = 0
        passlog = os.path.splitext(out_path)[0] + ".passlog"
        if two_pass and bitrate:
            progress.log("[dim]Pass 1/2 (analysis)…[/dim]")
            return_code = await run_cmd(build_cmd(pass_num=1, passlog=passlog, to_null=True))
            if return_code == 0:
                progress.log("[dim]Pass 2/2 (encode)…[/dim]")
                return_code = await run_cmd(build_cmd(pass_num=2, passlog=passlog, to_null=False))
            try:
                for ext in (".log", ".log.mbtree", "-0.log", "-0.log.mbtree"):
                    maybe = passlog + ext
                    if os.path.exists(maybe):
                        os.remove(maybe)
            except Exception:
                pass
        else:
            return_code = await run_cmd(build_cmd())

        if return_code == 0:
            progress.set_progress(100, status="Done ✔")
            try:
                size = os.path.getsize(out_path)
                progress.log(f"[green]Complete:[/green] {out_path} ({format_bytes(size)})")
            except Exception:
                progress.log(f"[green]Complete:[/green] {out_path}")
        else:
            progress.log("[red]Conversion failed[/red]")


if __name__ == "__main__":
    app = ChongaApp()
    app.run()


