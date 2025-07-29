# Chonga Media Converter
![getchinga](<chonga.png>)

Chonga is a command-line tool for converting video files to the space-efficient WebM format using the VP9 codec. It provides a user-friendly terminal interface with a progress bar to monitor the conversion process. It deletes the audio track. usually 90% file savings focused on video quality preservation. 

## Features

-   Converts various video formats to WebM.
-   Uses `ffmpeg` for robust and high-quality encoding.
-   Displays a progress bar with time remaining.
-   Customizable bitrate for output files.
 


## Requirements

-   Python 3
-   FFmpeg 

You can install FFmpeg on macOS using Homebrew:

```bash
brew install ffmpeg
```

For other operating systems, please refer to the official [FFmpeg documentation](https://ffmpeg.org/download.html).

## Installation

1.  Clone the repository:

    ```bash
    git clone https://github.com/your-username/chonga.git
    cd chonga
    ```

2.  Install the required Python packages:

    ```bash
    pip install -r requirements.txt
    ```

## Usage

The main application is `chonga_tui.py`. You can run it from the command line with the following arguments:

```bash
python chonga_tui.py [INPUT_FILE] [OUTPUT_FILE] [OPTIONS]
```

### Arguments

-   `input`: Path to the source video file.
-   `output`: Path for the converted WebM file.
-   `-b, --bitrate`: (Optional) Video bitrate for the output file (e.g., `1M`, `500k`). Defaults to `1M`.

### Example

```bash
python chonga_tui.py my_video.mp4 my_video.webm --bitrate 500k
```

## Alternative Script

The repository also contains a simple Bash script, `chonga`, for quick conversions without the TUI.

### Usage

```bash
./chonga video1.mp4 video2.mov
```

This will convert `video1.mp4` to `video1.webm` and `video2.mov` to `video2.webm`.