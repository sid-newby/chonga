#!/usr/bin/env python3
"""
Yo Changa, Es a Chinga? 
"""

import argparse
import os
import platform
import subprocess
from typing import Optional
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn

console = Console()

def print_banner():
    console.print(r"""
   🌮🌮🌮  ¡Bienvenidos a la Chinga Converter!  🌮🌮🌮
    _   _                     
   / |_| \ _   _   ___  _ __  
  |   _   | | | | / _ \| '_ \ 
  |  | |  | |_| ||  __/| | | |
  |_|_| |_|\__,_| \___||_| |_|
  
   Sombreros 🤠  Tacos 🌮  Punk Rock 🤘
    """, style="bold magenta", justify="center")

def get_duration(path: str) -> float:
    """Use ffprobe to get total duration in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        return float(result.stdout.strip())
    except:
        console.print("Error: Could not determine file duration.", style="bold red")
        raise

def get_video_dimensions(path: str) -> Optional[tuple[int, int]]:
    """Return (width, height) of the first video stream using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
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

def choose_vp9_tiling(width: Optional[int], height: Optional[int]) -> tuple[int, int]:
    """Heuristic for VP9 tiling.

    - tile-columns is log2 of columns. More columns improve multi-thread scaling.
    - tile-rows is log2 of rows. Usually 0-1 is enough; 1 for very tall/high-res.
    """
    if width is None or height is None:
        return 1, 0  # safe defaults
    # columns: up to 4 (16 cols) for 4K and above
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

def parse_time_to_seconds(time_str: str) -> Optional[float]:
    """Parse an ffmpeg out_time string (HH:MM:SS.micro) into seconds.

    Returns None if parsing fails or the value is N/A.
    """
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
    """Convert strings like '500k', '2M' to bits per second.

    Returns None if format is unrecognized.
    """
    if not bitrate_str:
        return None
    s = bitrate_str.strip().lower()
    try:
        if s.endswith("k"):
            return int(float(s[:-1]) * 1_000)
        if s.endswith("m"):
            return int(float(s[:-1]) * 1_000_000)
        # plain number means bits per second
        return int(float(s))
    except Exception:
        return None

def convert(
    input_path: str,
    output_path: str,
    bitrate: Optional[str],
    crf: int,
    speed: int,
    threads: Optional[int],
    tile_columns: Optional[int],
    tile_rows: Optional[int],
    aq_mode: int,
    deadline: str,
    enable_hwdec: bool,
    two_pass: bool,
):
    """Run ffmpeg with progress parsing and rich progress bar.

    If `bitrate` is provided, encodes at that bitrate. Otherwise uses CRF mode with `-b:v 0`.
    """
    duration = get_duration(input_path)
    task_id = None

    mode_desc = f"CRF {crf} (quality-targeted)" if not bitrate else f"Bitrate {bitrate} (size-targeted)"
    console.print(f"Converting [bold]{input_path}[/bold] → [bold]{output_path}[/bold] • [cyan]{mode_desc}[/cyan]", justify="center")

    # Optional advisory if bitrate likely yields a large output
    if bitrate:
        bps = parse_bitrate_to_bps(bitrate)
        if bps:
            est_bytes = (bps / 8.0) * duration
            try:
                src_bytes = os.path.getsize(input_path)
                if est_bytes > src_bytes * 1.05:  # >5% larger than source
                    est_mb = est_bytes / (1024 * 1024)
                    console.print(
                        f"[yellow]Note:[/yellow] Target bitrate implies ~{est_mb:.1f} MB output; this may exceed source size.",
                        justify="center",
                    )
            except Exception:
                pass
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("🔥 Chingaderas in progress...", total=duration)
        # Probe dimensions for tiling
        dims = get_video_dimensions(input_path)
        width, height = (dims if dims else (None, None))
        auto_cols, auto_rows = choose_vp9_tiling(width, height)
        cols = tile_columns if tile_columns is not None and tile_columns >= 0 else auto_cols
        rows = tile_rows if tile_rows is not None and tile_rows >= 0 else auto_rows
        max_threads = threads if threads and threads > 0 else os.cpu_count() or 4

        def build_cmd(pass_num: Optional[int] = None, passlog: Optional[str] = None, null_output: bool = False):
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
            ]
            if enable_hwdec and platform.system() == "Darwin":
                cmd += ["-hwaccel", "videotoolbox"]
            cmd += [
                "-i", input_path,
                "-an",
                "-c:v", "libvpx-vp9",
                "-pix_fmt", "yuv420p",
                "-row-mt", "1",
                "-tile-columns", str(cols),
                "-tile-rows", str(rows),
                "-threads", str(max_threads),
                "-aq-mode", str(aq_mode),
                "-deadline", deadline,
                "-cpu-used", str(speed),
                "-auto-alt-ref", "1",
                "-lag-in-frames", "25",
            ]
            if bitrate:
                cmd += ["-b:v", bitrate]
            else:
                cmd += ["-crf", str(crf), "-b:v", "0"]
            if pass_num is not None and passlog is not None:
                cmd += ["-pass", str(pass_num), "-passlogfile", passlog]
            cmd += ["-progress", "pipe:1", "-nostats"]
            if null_output:
                cmd += ["-f", "null", "/dev/null"]
            else:
                cmd += [output_path]
            return cmd

        def run_with_progress(cmd):
            proc_local = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            while True:
                line = proc_local.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("out_time_ms="):
                    value = line.split("=", 1)[1].strip()
                    if value.isdigit():
                        microseconds = int(value)
                        seconds = microseconds / 1_000_000
                        progress.update(task_id, completed=min(seconds, duration))
                elif line.startswith("out_time="):
                    ts = line.split("=", 1)[1].strip()
                    seconds = parse_time_to_seconds(ts)
                    if seconds is not None:
                        progress.update(task_id, completed=min(seconds, duration))
                elif line.startswith("progress=") and "end" in line:
                    break
            proc_local.wait()
            return proc_local.returncode

        return_code = 0
        if two_pass and bitrate:
            passlog = os.path.splitext(output_path)[0] + ".passlog"
            console.print("[dim]Pass 1/2 (analysis)...[/dim]", justify="center")
            return_code = run_with_progress(build_cmd(pass_num=1, passlog=passlog, null_output=True))
            if return_code == 0:
                console.print("[dim]Pass 2/2 (encode)...[/dim]", justify="center")
                return_code = run_with_progress(build_cmd(pass_num=2, passlog=passlog, null_output=False))
            # Cleanup pass logs if present
            try:
                for ext in (".log", ".log.mbtree", "-0.log", "-0.log.mbtree"):
                    maybe = passlog + ext
                    if os.path.exists(maybe):
                        os.remove(maybe)
            except Exception:
                pass
        else:
            return_code = run_with_progress(build_cmd())

    if return_code == 0:
        console.print("\n✅ Conversion complete! Enjoy your tiny chinga.", style="bold green", justify="center")
    else:
        console.print("\n❌ Conversion failed!", style="bold red", justify="center")

def main():
    parser = argparse.ArgumentParser(
        description="Tacos & sombreros shrink MP4 → WebM with tacos & sombreros"
    )
    parser.add_argument("input", help="Path to the big MP4 (changa)")
    parser.add_argument("output", help="Path for the tiny WebM (chinga)")
    parser.add_argument(
        "-b", "--bitrate", default=None,
        help="Target average video bitrate (e.g., '1M', '500k'). If omitted, CRF mode is used."
    )
    parser.add_argument(
        "--crf", type=int, default=30,
        help="CRF quality for VP9 (lower is higher quality, typical 18-36). Used when --bitrate is not set."
    )
    parser.add_argument(
        "--speed", type=int, default=1,
        help="VP9 encoding speed/quality tradeoff (-cpu-used). 0=best quality, 4=faster with some quality loss."
    )
    parser.add_argument(
        "--threads", type=int, default=0,
        help="Max threads for the encoder. Defaults to all logical CPUs."
    )
    parser.add_argument(
        "--tile-columns", type=int, default=-1,
        help="VP9 tile-columns (log2). -1=auto by resolution."
    )
    parser.add_argument(
        "--tile-rows", type=int, default=-1,
        help="VP9 tile-rows (log2). -1=auto by resolution."
    )
    parser.add_argument(
        "--aq-mode", type=int, default=1,
        help="VP9 AQ mode (0=off, 1=variance AQ)."
    )
    parser.add_argument(
        "--deadline", type=str, default="good",
        choices=["good", "best", "realtime"],
        help="libvpx deadline preset. 'good' is a balanced default."
    )
    parser.add_argument(
        "--hwdec", action="store_true",
        help="Enable hardware-accelerated decoding (videotoolbox on macOS)."
    )
    parser.add_argument(
        "--two-pass", action="store_true",
        help="Use two-pass encoding when --bitrate is set (better quality/size)."
    )
    args = parser.parse_args()
    print_banner()
    convert(
        args.input,
        args.output,
        args.bitrate,
        args.crf,
        args.speed,
        args.threads if args.threads and args.threads > 0 else None,
        args.tile_columns if args.tile_columns is not None else None,
        args.tile_rows if args.tile_rows is not None else None,
        args.aq_mode,
        args.deadline,
        args.hwdec,
        args.two_pass,
    )

if __name__ == "__main__":
    main()
