# Video Downloader

Simple desktop video downloader built with Tkinter and [`yt-dlp`](https://github.com/yt-dlp/yt-dlp).

## What this project does

This repository contains a single Python GUI application: `yt-dlp_gui_wrapper.py`.

The app lets users:

- paste one or more video URLs
- choose video, audio, or video+audio downloads
- select quality and output container
- extract audio to common formats
- download playlists
- download/embed subtitles
- embed thumbnails, metadata, and chapters
- load browser cookies for restricted content
- cancel active downloads

## Dependencies

### Python dependency

Install the required Python package:

```bash
pip install -r requirements.txt
```

### System dependencies

- **Python 3.10 or newer**
- **ffmpeg** available on your `PATH`

### Optional dependency

For many YouTube downloads, `yt-dlp` benefits from a JavaScript runtime for challenge solving:

- **Deno** or
- **Node.js**

## Installation

1. Make sure Python 3.10+ is installed.
2. Install `ffmpeg`.
3. Install Python packages:

   ```bash
   pip install -r requirements.txt
   ```

4. Optionally install **Deno** or **Node.js** for improved YouTube compatibility.

## Running the app

From the repository root:

```bash
python yt-dlp_gui_wrapper.py
```

## General information for users

- Settings are saved in `~/.video_downloader.json`.
- The default download folder is your local `Downloads` directory.
- Audio extraction, subtitle embedding, metadata embedding, and thumbnail embedding rely on `ffmpeg`.
- Browser cookies can help with age-restricted, private, or login-required videos.
- If `yt-dlp` is outdated, the app warns you and may ask you to upgrade it.

## Repository contents

- `yt-dlp_gui_wrapper.py` - the full GUI application
- `requirements.txt` - Python dependency list
