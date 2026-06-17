# Video Downloader

A simple desktop GUI for [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), built with
Python's standard-library **Tkinter** toolkit. Paste one or more video URLs (one
per line), pick the quality and format you want, and download — no command line
required. It works with any site that yt-dlp supports (YouTube, Vimeo, and
[hundreds more](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)).

The whole app is a single file: `yt-dlp_gui_wrapper.py`.

---

## Features

- **Quality picker** — Best/Worst available, or a fixed cap from 2160p (4K) down
  to 144p.
- **Download type** — Video + Audio, Video only, or Audio only.
- **Audio extraction** — save audio as `mp3`, `m4a`, `opus`, `wav`, or `flac`,
  with a selectable bitrate (96–320 kbps).
- **Output container** — prefer `mp4`, `mkv`, or `webm` for merged video.
- **Playlists** — opt in to downloading a whole playlist when the URL is one.
- **Subtitles** — download subtitles (including auto-generated), choose
  languages, and optionally embed them into the video file.
- **Embedding** — embed the thumbnail, and embed metadata + chapters.
- **Speed limit** — throttle the download rate (KB/s).
- **Browser cookies** — pull cookies from Chrome, Firefox, Edge, Safari, Brave,
  Opera, or Chromium for age-restricted / private / members-only videos.
- **Custom filename template** — full yt-dlp output-template support
  (default `%(title)s.%(ext)s`).
- **YouTube JS challenge solver** — automatically uses Deno or Node.js (if
  available) to solve YouTube's "n" challenge, avoiding HTTP 403 failures.
- **Live progress** — progress bar, status line (speed / ETA), and a scrollable
  log of yt-dlp output.
- **Cancel** an in-progress download at any time.
- **Quality-of-life** — paste URLs from the clipboard, clear buttons, "Open"
  the output folder, and **settings are remembered between runs**.

---

## Requirements

### Dependencies

| Dependency | Required? | Purpose | Install |
|------------|-----------|---------|---------|
| **Python ≥ 3.10** | Required | Runtime. 3.10+ is needed for the YouTube JS-challenge solver. | [python.org](https://www.python.org/downloads/) |
| **Tkinter** | Required | The GUI toolkit. | Bundled with most Python installs (see note below). |
| **yt-dlp** | Required | The actual download engine. | `pip install yt-dlp` |
| **FFmpeg** | Required for most uses | Merging video+audio, converting audio, embedding subs/thumbnails/metadata. | See [ffmpeg.org](https://ffmpeg.org/download.html) |
| **Deno** *or* **Node.js** | Recommended | Solves YouTube's JavaScript "n" challenge; without it many YouTube videos fail with HTTP 403. | `brew install deno` / [nodejs.org](https://nodejs.org/) |

> **Tkinter note:** Tkinter ships with the official Python installers on Windows
> and macOS. On some Linux distros it's a separate package, e.g.
> `sudo apt install python3-tk` (Debian/Ubuntu) or
> `sudo dnf install python3-tkinter` (Fedora).

### Quick install

```bash
# 1. yt-dlp (the download engine)
python -m pip install -U yt-dlp

# 2. FFmpeg (pick the one for your OS)
#    macOS:           brew install ffmpeg
#    Debian/Ubuntu:   sudo apt install ffmpeg
#    Windows:         winget install Gyan.FFmpeg   (or download a build manually)

# 3. (Recommended) a JS runtime for YouTube
#    macOS:           brew install deno
#    Anywhere:        install Node.js from https://nodejs.org
```

---

## Running

```bash
python yt-dlp_gui_wrapper.py
```

That's it — the application window opens. On first launch it defaults to saving
into your `~/Downloads` folder.

> **Auto-relaunch:** If you start the script with an older/incapable Python, it
> will try to find and re-launch itself under a Python ≥ 3.10 whose yt-dlp
> supports the JS-challenge solver, so it "just works" however you start it
> (terminal, IDE, or double-click). Set the environment variable
> `VD_NO_RELAUNCH=1` to disable this behaviour.

---

## Using the app

1. **Paste URLs** into the top box, one per line. Use **Paste** to grab from the
   clipboard, or **Clear** to empty the box.
2. **Choose a save folder** under *Save to* (**Browse…** to pick one, **Open** to
   reveal it in your file manager).
3. **Pick quality & format:**
   - *Download* — Video + Audio / Video only / Audio only.
   - *Quality* — resolution cap (or Best/Worst).
   - *Container* — output format for video (enabled for video downloads).
   - *Audio* — codec + bitrate (enabled for "Audio only").
4. **Set options** as needed — playlist, subtitles (+ languages, + embed),
   thumbnail, metadata/chapters, speed limit, browser cookies, filename
   template, and the YouTube JS-challenge toggle.
5. Click **Download**. Watch the progress bar, status line, and log. Click
   **Cancel** to stop.

Your settings (everything except the URL list) are saved to
`~/.video_downloader.json` when you close the window and restored next time.

---

## Example uses

**Download a single YouTube video at 1080p as MP4**
1. Paste the video URL.
2. *Download* = `Video + Audio`, *Quality* = `1080p (Full HD)`, *Container* = `mp4`.
3. Click **Download**.

**Rip audio from a video as a 320 kbps MP3**
1. Paste the URL.
2. *Download* = `Audio only`, *Audio* = `mp3` / `320`.
3. Click **Download**.

**Download an entire playlist at 720p**
1. Paste the playlist URL.
2. Tick **Download playlist (if URL is one)**.
3. *Quality* = `720p (HD)`.
4. Click **Download**.

**Get a video with English + Spanish subtitles burned in**
1. Paste the URL.
2. Tick **Download subtitles** and **Embed subtitles**.
3. Set *Sub langs* to `en,es`.
4. Click **Download**.

**Download a private / age-restricted video using your browser login**
1. Paste the URL.
2. Set *Cookies from* to the browser you're logged into (e.g. `firefox`).
3. Click **Download**.

**Archive a channel with thumbnails, metadata, and a tidy filename**
1. Paste the channel/playlist URL and tick **Download playlist**.
2. Tick **Embed thumbnail** and **Embed metadata & chapters**.
3. Set *Filename template* to e.g. `%(uploader)s/%(upload_date)s - %(title)s.%(ext)s`.
4. Click **Download**.

---

## Troubleshooting

- **"yt-dlp is not installed"** — run `pip install yt-dlp` for the *same* Python
  you launch the app with.
- **Merging / audio conversion / embedding fails** — FFmpeg isn't on your `PATH`.
  Install it (see above) and make sure `ffmpeg -version` works in a terminal.
- **YouTube videos fail with HTTP 403 / "not available" / SABR errors** — install
  Deno or Node.js so the JS-challenge solver can run, and keep the
  **Solve YouTube JS challenges** option ticked. The log will tell you whether a
  runtime was found.
- **"this yt-dlp is too old…" warning** — upgrade with
  `python -m pip install -U yt-dlp`. YouTube changes frequently; staying current
  matters.
- **Private/region-locked content** — use the *Cookies from* option with a
  browser where you're logged in / in the right region.

---

## How it works

The GUI runs downloads on a background thread and communicates with the main
(Tk) thread through a message queue, so the interface stays responsive and can
show live progress, stream yt-dlp's log, and cancel cleanly. It calls yt-dlp's
Python API directly (`yt_dlp.YoutubeDL`) rather than shelling out, building an
options dict from your selections and attaching the appropriate post-processors
(audio extraction, subtitle/thumbnail/metadata embedding).

---

## Notes & caveats

- Only download content you have the right to download; respect each site's terms
  of service and your local laws.
- The app is a thin convenience layer — anything yt-dlp can't do, it can't do
  either. For advanced needs, yt-dlp's CLI offers far more knobs.

---

*Author: Leo Fitzgerald*
