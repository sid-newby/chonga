#!/usr/bin/env python3
"""
Chaotic Mexican-American punk TUI: convert a “changa” (MP4) into a tiny “chinga” (WebM)
with sombreros, tacos, enchiladas, rich progress bars, and total mayhem.
"""

import argparse
import subprocess
import re
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

def convert(input_path: str, output_path: str, bitrate: str):
    """Run ffmpeg with progress parsing and rich progress bar."""
    duration = get_duration(input_path)
    task_id = None

    console.print(f"Converting [bold]{input_path}[/bold] → [bold]{output_path}[/bold] at [cyan]{bitrate}[/cyan]", justify="center")
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("🔥 Chinga in progress...", total=duration)
        # ffmpeg -progress pipe:1 prints key=value lines to stdout
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", input_path,
            "-c:v", "libvpx-vp9",
            "-b:v", bitrate,
            "-progress", "pipe:1",
            "-nostats",
            output_path
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Parse progress lines
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if line.startswith("out_time_ms="):
                ms = int(line.split("=")[1])
                seconds = ms / 1_000_000
                progress.update(task_id, completed=min(seconds, duration))
            elif line.startswith("progress=") and "end" in line:
                break

        proc.wait()

    if proc.returncode == 0:
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
        "-b", "--bitrate", default="1M",
        help="Video bitrate for WebM (e.g., '1M', '500k')"
    )
    args = parser.parse_args()
    print_banner()
    convert(args.input, args.output, args.bitrate)

if __name__ == "__main__":
    main()
