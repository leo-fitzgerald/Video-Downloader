"""
17.06.2026 - Leo Fitzgerald

Tkinter video downloader

A GUI wrapper around yt-dlp. Paste one or more video URLs (one per line),
choose quality/format and options,then download. Works for any site yt-dlp support.

Features:
    - Resolution / quality picker (4K down to 144p, plus best/worst)
    - Download type: video+audio, video-only, or audio-only
    - Audio extraction to mp3/m4a/opus/wav/flac with a quality setting
    - Preferred output container (mp4/mkv/webm)
    - Playlist toggle
    - Subtitles: download + optional embedding, with language selection
    - Embed thumbnail, metadata and chapters
    - Download speed limit
    - Load cookies from a browser (for age-restricted / private videos)
    - Custom output filename template
    - Cancel an in-progress download
    - Paste from clipboard, clear buttons, open output folder
    - Remembers settings between runs

Requirements:
    pip install yt-dlp
    ffmpeg on PATH (needed for merging, audio extraction, and embedding)

Run:
    python video_downloader.py
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import yt_dlp
except ImportError:  # pragma: no cover - shown to the user at runtime
    yt_dlp = None


CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".video_downloader.json")

# Resolution label -> max height (None means no height cap).
QUALITY_OPTIONS = {
    "Best available": None,
    "2160p (4K)": 2160,
    "1440p (2K)": 1440,
    "1080p (Full HD)": 1080,
    "720p (HD)": 720,
    "480p": 480,
    "360p": 360,
    "240p": 240,
    "144p": 144,
    "Worst available": "worst",
}


def detect_js_runtimes():
    """Locate a JavaScript runtime (Deno or Node) for solving YouTube's "n"
    challenge.

    Searches PATH first, then common install dirs. This matters because a GUI
    launched from Finder, an IDE, or a packaged app inherits a minimal PATH
    (often just /usr/bin:/bin) that omits ~/.local/bin, Homebrew, etc., so a
    plain shutil.which() would miss a runtime that clearly works from a shell.

    Returns a dict suitable for yt-dlp's ``js_runtimes`` option, e.g.
    ``{"node": {"path": "/Users/x/.local/bin/node"}}`` (empty if none found).
    """
    extra_dirs = [
        os.path.expanduser("~/.deno/bin"),
        os.path.expanduser("~/.local/bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
    ]
    found = {}
    for rt in ("deno", "node"):  # Deno first: yt-dlp's preferred runtime
        path = shutil.which(rt)
        if not path:
            for d in extra_dirs:
                cand = os.path.join(d, rt)
                if os.path.isfile(cand) and os.access(cand, os.X_OK):
                    path = cand
                    break
        if path:
            found[rt] = {"path": path}
    return found


def ytdlp_supports_js_solver():
    """True if the installed yt-dlp understands the JS-challenge-solver options
    (``--remote-components`` / ``--js-runtimes``).

    Older yt-dlp builds (pre ~late-2025) predate YouTube's "n" challenge solver.
    They silently *ignore* unknown ``js_runtimes``/``remote_components`` params,
    so the download falls back to format 18 and fails with HTTP 403. Detecting
    the capability lets us tell the user to upgrade instead of failing opaquely.
    """
    try:
        from yt_dlp.options import create_parser
        return create_parser().has_option("--remote-components")
    except Exception:  # noqa: BLE001 - any import/parse problem -> assume no
        return False


def find_capable_python():
    """Return the path to a Python >= 3.10 whose yt-dlp supports the JS-challenge
    solver, or None.

    The solver (and a downloadable YouTube experience) needs yt-dlp built for
    Python 3.10+. If this script is launched with an older interpreter (e.g. a
    system or legacy-conda Python 3.9), we look for a better one to relaunch
    under, so the user doesn't have to know which `python` to invoke.
    """
    probe = (
        "import sys\n"
        "if sys.version_info < (3, 10): sys.exit(1)\n"
        "try:\n"
        "    from yt_dlp.options import create_parser\n"
        "    sys.exit(0 if create_parser().has_option('--remote-components') else 1)\n"
        "except Exception:\n"
        "    sys.exit(1)\n"
    )
    candidates = []
    for name in ("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"):
        p = shutil.which(name)
        if p:
            candidates.append(p)
    candidates += [
        os.path.expanduser("~/anaconda3/bin/python"),
        os.path.expanduser("~/miniconda3/bin/python"),
        os.path.expanduser("~/miniforge3/bin/python"),
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
    ]
    seen = set()
    for c in candidates:
        if not c or not os.path.exists(c):
            continue
        real = os.path.realpath(c)
        if real in seen:
            continue
        seen.add(real)
        try:
            if subprocess.run([c, "-c", probe], capture_output=True, timeout=20).returncode == 0:
                return c
        except Exception:  # noqa: BLE001 - unusable candidate, try the next
            continue
    return None


class DownloadCancelled(Exception):
    """Raised from the progress hook to abort the active download."""


class QueueLogger:
    """Routes yt-dlp's own log output into the GUI log via the message queue.

    Without this, errors raised internally by yt-dlp (DRM, unavailable video,
    geo-block, missing format, ...) are invisible and the run looks "finished"
    even though nothing downloaded.
    """

    def __init__(self, msg_queue):
        self.msg_queue = msg_queue
        self.errors = 0

    def debug(self, msg):
        # yt-dlp sends both debug and plain info lines here. Drop the noisy
        # [debug] lines and the per-chunk download progress (handled elsewhere).
        if msg.startswith("[debug] "):
            return
        if msg.startswith("[download]") and "%" in msg:
            return
        self.msg_queue.put(("log", "  " + msg.strip()))

    def info(self, msg):
        self.msg_queue.put(("log", "  " + msg.strip()))

    def warning(self, msg):
        self.msg_queue.put(("log", "  WARNING: " + msg.strip()))

    def error(self, msg):
        self.errors += 1
        self.msg_queue.put(("log", "  ERROR: " + msg.strip()))


class DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Downloader")
        self.root.geometry("700x820")
        self.root.minsize(620, 720)

        # Worker thread -> GUI communication. The worker never touches Tk
        # widgets directly; it pushes messages onto this queue and the GUI polls.
        self.msg_queue = queue.Queue()
        self.worker = None
        self.cancel_event = threading.Event()
        self.last_dest = None
        self._poll_id = None       # id of the pending after() callback
        self._closing = False      # set on shutdown to stop the poll loop

        # --- bound variables (also the persisted settings) ---
        self.dest_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        self.dtype_var = tk.StringVar(value="Video + Audio")
        self.quality_var = tk.StringVar(value="Best available")
        self.container_var = tk.StringVar(value="mp4")
        self.audio_format_var = tk.StringVar(value="mp3")
        self.audio_quality_var = tk.StringVar(value="192")
        self.playlist_var = tk.BooleanVar(value=False)
        self.subs_var = tk.BooleanVar(value=False)
        self.embed_subs_var = tk.BooleanVar(value=True)
        self.sub_lang_var = tk.StringVar(value="en")
        self.thumb_var = tk.BooleanVar(value=False)
        self.metadata_var = tk.BooleanVar(value=True)
        self.jschallenge_var = tk.BooleanVar(value=True)
        self.ratelimit_var = tk.StringVar(value="")
        self.cookies_var = tk.StringVar(value="none")
        self.template_var = tk.StringVar(value="%(title)s.%(ext)s")
        self.status_var = tk.StringVar(value="Ready")

        self._persisted = {
            "dest": self.dest_var,
            "dtype": self.dtype_var,
            "quality": self.quality_var,
            "container": self.container_var,
            "audio_format": self.audio_format_var,
            "audio_quality": self.audio_quality_var,
            "playlist": self.playlist_var,
            "subs": self.subs_var,
            "embed_subs": self.embed_subs_var,
            "sub_lang": self.sub_lang_var,
            "thumb": self.thumb_var,
            "metadata": self.metadata_var,
            "jschallenge": self.jschallenge_var,
            "ratelimit": self.ratelimit_var,
            "cookies": self.cookies_var,
            "template": self.template_var,
        }

        self._load_settings()
        self._build_widgets()
        self._on_type_change()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_id = self.root.after(100, self._poll_queue)

    # ------------------------------------------------------------------ UI ---
    def _build_widgets(self):
        pad = {"padx": 10, "pady": (8, 0)}

        # URLs
        url_frame = ttk.LabelFrame(self.root, text="Video URLs (one per line)")
        url_frame.pack(fill="x", **pad)
        self.url_text = tk.Text(url_frame, height=5, wrap="none")
        self.url_text.pack(fill="x", padx=8, pady=8, side="left", expand=True)
        url_btns = ttk.Frame(url_frame)
        url_btns.pack(side="right", fill="y", padx=(0, 8), pady=8)
        ttk.Button(url_btns, text="Paste", command=self._paste).pack(fill="x")
        ttk.Button(url_btns, text="Clear", command=lambda: self.url_text.delete("1.0", "end")).pack(
            fill="x", pady=(4, 0)
        )

        # Destination
        dest_frame = ttk.LabelFrame(self.root, text="Save to")
        dest_frame.pack(fill="x", **pad)
        inner = ttk.Frame(dest_frame)
        inner.pack(fill="x", padx=8, pady=8)
        ttk.Entry(inner, textvariable=self.dest_var).pack(side="left", fill="x", expand=True)
        ttk.Button(inner, text="Browse...", command=self._browse).pack(side="left", padx=(5, 0))
        ttk.Button(inner, text="Open", command=self._open_folder).pack(side="left", padx=(5, 0))

        # Quality / format
        qf = ttk.LabelFrame(self.root, text="Quality & format")
        qf.pack(fill="x", **pad)
        grid = ttk.Frame(qf)
        grid.pack(fill="x", padx=8, pady=8)

        ttk.Label(grid, text="Download:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(
            grid, textvariable=self.dtype_var, state="readonly", width=16,
            values=["Video + Audio", "Video only", "Audio only"],
        ).grid(row=0, column=1, sticky="w", padx=5)
        self.dtype_var.trace_add("write", lambda *_: self._on_type_change())

        ttk.Label(grid, text="Quality:").grid(row=0, column=2, sticky="w", padx=(15, 0))
        ttk.Combobox(
            grid, textvariable=self.quality_var, state="readonly", width=18,
            values=list(QUALITY_OPTIONS.keys()),
        ).grid(row=0, column=3, sticky="w", padx=5)

        ttk.Label(grid, text="Container:").grid(row=1, column=0, sticky="w", pady=3)
        self.container_combo = ttk.Combobox(
            grid, textvariable=self.container_var, state="readonly", width=16,
            values=["mp4", "mkv", "webm"],
        )
        self.container_combo.grid(row=1, column=1, sticky="w", padx=5)

        ttk.Label(grid, text="Audio:").grid(row=1, column=2, sticky="w", padx=(15, 0))
        self.audio_format_combo = ttk.Combobox(
            grid, textvariable=self.audio_format_var, state="readonly", width=8,
            values=["mp3", "m4a", "opus", "wav", "flac"],
        )
        self.audio_format_combo.grid(row=1, column=3, sticky="w", padx=5)
        self.audio_quality_combo = ttk.Combobox(
            grid, textvariable=self.audio_quality_var, state="readonly", width=7,
            values=["320", "256", "192", "128", "96"],
        )
        self.audio_quality_combo.grid(row=1, column=4, sticky="w", padx=5)

        # Options
        opt = ttk.LabelFrame(self.root, text="Options")
        opt.pack(fill="x", **pad)
        og = ttk.Frame(opt)
        og.pack(fill="x", padx=8, pady=8)

        ttk.Checkbutton(og, text="Download playlist (if URL is one)", variable=self.playlist_var).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=2
        )
        ttk.Checkbutton(og, text="Embed thumbnail", variable=self.thumb_var).grid(
            row=0, column=2, sticky="w", padx=(15, 0), pady=2
        )
        ttk.Checkbutton(og, text="Embed metadata & chapters", variable=self.metadata_var).grid(
            row=1, column=2, sticky="w", padx=(15, 0), pady=2
        )

        ttk.Checkbutton(
            og, text="Download subtitles", variable=self.subs_var, command=self._on_type_change
        ).grid(row=1, column=0, sticky="w", pady=2)
        self.embed_subs_cb = ttk.Checkbutton(og, text="Embed subtitles", variable=self.embed_subs_var)
        self.embed_subs_cb.grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(og, text="Sub langs:").grid(row=2, column=0, sticky="w", pady=2)
        self.sub_lang_entry = ttk.Entry(og, textvariable=self.sub_lang_var, width=18)
        self.sub_lang_entry.grid(row=2, column=1, sticky="w", pady=2)

        ttk.Label(og, text="Speed limit (KB/s):").grid(row=3, column=0, sticky="w", pady=2)
        ttk.Entry(og, textvariable=self.ratelimit_var, width=10).grid(row=3, column=1, sticky="w")
        ttk.Label(og, text="Cookies from:").grid(row=3, column=2, sticky="w", padx=(15, 0))
        ttk.Combobox(
            og, textvariable=self.cookies_var, state="readonly", width=10,
            values=["none", "chrome", "firefox", "edge", "safari", "brave", "opera", "chromium"],
        ).grid(row=3, column=3, sticky="w", padx=5)

        ttk.Label(og, text="Filename template:").grid(row=4, column=0, sticky="w", pady=2)
        ttk.Entry(og, textvariable=self.template_var).grid(
            row=4, column=1, columnspan=4, sticky="we", pady=2
        )

        ttk.Checkbutton(
            og,
            text="Solve YouTube JS challenges (recommended; needs Deno or Node.js)",
            variable=self.jschallenge_var,
        ).grid(row=5, column=0, columnspan=5, sticky="w", pady=(6, 0))
        og.columnconfigure(1, weight=1)

        # Controls
        ctrl = ttk.Frame(self.root)
        ctrl.pack(fill="x", padx=10, pady=10)
        self.download_btn = ttk.Button(ctrl, text="Download", command=self._start_download)
        self.download_btn.pack(side="left", fill="x", expand=True)
        self.cancel_btn = ttk.Button(ctrl, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))

        # Progress
        self.progress = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=10)

        # Log
        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        self.log = tk.Text(log_frame, height=8, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=8, pady=8, side="left")
        sb = ttk.Scrollbar(log_frame, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set)
        ttk.Button(log_frame, text="Clear", command=self._clear_log).pack(side="bottom")

        # Status bar
        ttk.Label(self.root, textvariable=self.status_var, anchor="w", relief="sunken").pack(
            fill="x", side="bottom"
        )

    def _on_type_change(self):
        """Enable/disable widgets that only apply to certain download types."""
        dtype = self.dtype_var.get()
        is_audio = dtype == "Audio only"
        is_video = dtype != "Audio only"

        self.container_combo.configure(state="disabled" if is_audio else "readonly")
        self.audio_format_combo.configure(state="readonly" if is_audio else "disabled")
        self.audio_quality_combo.configure(state="readonly" if is_audio else "disabled")

        subs_on = self.subs_var.get() and is_video
        self.embed_subs_cb.configure(state="normal" if subs_on else "disabled")
        self.sub_lang_entry.configure(state="normal" if subs_on else "disabled")

    # -------------------------------------------------------------- helpers ---
    def _browse(self):
        folder = filedialog.askdirectory(initialdir=self.dest_var.get() or os.getcwd())
        if folder:
            self.dest_var.set(folder)

    def _paste(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return
        if text:
            current = self.url_text.get("1.0", "end").strip()
            self.url_text.insert("end", ("\n" if current else "") + text.strip())

    def _open_folder(self):
        path = self.last_dest or self.dest_var.get()
        if not path or not os.path.isdir(path):
            messagebox.showinfo("Open folder", "Folder does not exist yet.")
            return
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            elif os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Open folder", str(exc))

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _log_line(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # -------------------------------------------------------- yt-dlp options ---
    def _build_ydl_opts(self, dest):
        opts = {
            "outtmpl": os.path.join(dest, self.template_var.get() or "%(title)s.%(ext)s"),
            "ignoreerrors": True,
            "noplaylist": not self.playlist_var.get(),
            "progress_hooks": [self._progress_hook],
            "postprocessors": [],
        }

        dtype = self.dtype_var.get()
        cap = QUALITY_OPTIONS.get(self.quality_var.get())
        height_filter = f"[height<=?{cap}]" if isinstance(cap, int) else ""

        if dtype == "Audio only":
            opts["format"] = "worstaudio/worst" if cap == "worst" else "bestaudio/best"
            opts["postprocessors"].append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": self.audio_format_var.get(),
                "preferredquality": self.audio_quality_var.get(),
            })
        elif dtype == "Video only":
            base = "worstvideo" if cap == "worst" else "bestvideo"
            opts["format"] = f"{base}{height_filter}"
        else:  # Video + Audio
            if cap == "worst":
                opts["format"] = "worstvideo+worstaudio/worst"
            elif cap is None:
                opts["format"] = "bestvideo+bestaudio/best"
            else:
                opts["format"] = (
                    f"bestvideo{height_filter}+bestaudio/best{height_filter}/best"
                )
            if self.container_var.get():
                opts["merge_output_format"] = self.container_var.get()

        if self.subs_var.get() and dtype != "Audio only":
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            langs = [l.strip() for l in self.sub_lang_var.get().split(",") if l.strip()]
            opts["subtitleslangs"] = langs or ["en"]
            if self.embed_subs_var.get():
                opts["postprocessors"].append({"key": "FFmpegEmbedSubtitle"})

        if self.thumb_var.get():
            opts["writethumbnail"] = True
            opts["postprocessors"].append({"key": "EmbedThumbnail"})

        if self.metadata_var.get():
            opts["postprocessors"].append({"key": "FFmpegMetadata", "add_chapters": True})

        limit = self.ratelimit_var.get().strip()
        if limit:
            try:
                opts["ratelimit"] = float(limit) * 1024
            except ValueError:
                self.msg_queue.put(("log", f"  (ignored invalid speed limit: {limit})"))

        if self.cookies_var.get() and self.cookies_var.get() != "none":
            opts["cookiesfrombrowser"] = (self.cookies_var.get(),)

        # YouTube now requires solving a JavaScript "n" challenge for most
        # videos; without it, downloads fail with HTTP 403 / "not available" /
        # SABR-streaming errors. yt-dlp needs (a) a JS runtime and (b) the EJS
        # challenge-solver component, fetched once from yt-dlp's official repo.
        if self.jschallenge_var.get():
            if not ytdlp_supports_js_solver():
                ver = getattr(getattr(yt_dlp, "version", None), "__version__", "?")
                self.msg_queue.put((
                    "log",
                    f"  WARNING: this yt-dlp ({ver}) is too old for the YouTube JS "
                    "challenge solver, so videos may fail with HTTP 403. Upgrade it:  "
                    "python -m pip install -U yt-dlp",
                ))
            else:
                runtimes = detect_js_runtimes()
                if runtimes:
                    opts["js_runtimes"] = runtimes
                    opts["remote_components"] = ["ejs:github"]
                    names = ", ".join(f"{k} ({v['path']})" for k, v in runtimes.items())
                    self.msg_queue.put(("log", f"  JS challenge solver ENABLED via {names}"))
                else:
                    self.msg_queue.put((
                        "log",
                        "  WARNING: No JS runtime found (Deno/Node) on PATH or in common "
                        "locations. Most YouTube videos will fail with HTTP 403. "
                        "Install one, e.g.  brew install deno",
                    ))

        return opts

    # ------------------------------------------------------------ downloading ---
    def _start_download(self):
        if yt_dlp is None:
            messagebox.showerror(
                "Missing dependency",
                "yt-dlp is not installed.\n\nInstall it with:\n    pip install yt-dlp",
            )
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Busy", "A download is already in progress.")
            return

        urls = [u.strip() for u in self.url_text.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showwarning("No URLs", "Please enter at least one video URL.")
            return

        dest = self.dest_var.get().strip()
        if not dest:
            messagebox.showwarning("No destination", "Please choose a save folder.")
            return
        try:
            os.makedirs(dest, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Bad folder", str(exc))
            return
        self.last_dest = dest

        self.cancel_event.clear()
        self.download_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress["value"] = 0
        self.status_var.set("Starting...")

        opts = self._build_ydl_opts(dest)
        self.worker = threading.Thread(
            target=self._download_worker, args=(urls, opts), daemon=True
        )
        self.worker.start()

    def _cancel(self):
        if self.worker and self.worker.is_alive():
            self.cancel_event.set()
            self.status_var.set("Cancelling...")

    def _download_worker(self, urls, opts):
        """Runs in a background thread. Communicates via self.msg_queue only."""
        total = len(urls)
        logger = QueueLogger(self.msg_queue)
        opts["logger"] = logger
        ok = failed = 0
        ver = getattr(getattr(yt_dlp, "version", None), "__version__", "?")
        self.msg_queue.put(("log", f"yt-dlp {ver}  -  Python {'.'.join(map(str, sys.version_info[:3]))}"))
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                for i, url in enumerate(urls, start=1):
                    if self.cancel_event.is_set():
                        break
                    self.msg_queue.put(("log", f"[{i}/{total}] {url}"))
                    self.msg_queue.put(("status", f"Downloading {i} of {total}..."))
                    errors_before = logger.errors
                    try:
                        ret = ydl.download([url])
                    except DownloadCancelled:
                        break
                    except Exception as exc:  # noqa: BLE001 - report per-URL failure
                        self.msg_queue.put(("log", f"  ERROR: {exc}"))
                        ret = 1
                    if ret == 0 and logger.errors == errors_before:
                        ok += 1
                    else:
                        failed += 1
            if self.cancel_event.is_set():
                self.msg_queue.put(("done", f"Cancelled ({ok} done, {failed} failed)."))
            elif failed:
                self.msg_queue.put(("done", f"Finished: {ok} succeeded, {failed} failed."))
            else:
                self.msg_queue.put(("done", f"All {ok} download(s) finished successfully."))
        except Exception as exc:  # noqa: BLE001
            self.msg_queue.put(("done", f"Failed: {exc}"))

    def _progress_hook(self, d):
        if self.cancel_event.is_set():
            raise DownloadCancelled()
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                self.msg_queue.put(("progress", d.get("downloaded_bytes", 0) / total * 100))
            speed = (d.get("_speed_str") or "").strip()
            eta = (d.get("_eta_str") or "").strip()
            self.msg_queue.put(("status", f"Downloading... {speed}  ETA {eta}"))
        elif status == "finished":
            self.msg_queue.put(("progress", 100))
            self.msg_queue.put(("status", "Processing (merge / convert)..."))
            self.msg_queue.put(("log", f"  Saved: {os.path.basename(d.get('filename', ''))}"))

    def _poll_queue(self):
        """Drain worker messages and update widgets on the main thread."""
        if self._closing:
            return
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._log_line(payload)
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "progress":
                    self.progress["value"] = payload
                elif kind == "done":
                    self._log_line(payload)
                    self.status_var.set(payload)
                    self.download_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
        except queue.Empty:
            pass
        # Reschedule and remember the id so _on_close can cancel it; otherwise
        # the callback fires after destroy() -> 'invalid command name ..._poll_queue'.
        self._poll_id = self.root.after(100, self._poll_queue)

    # ------------------------------------------------------------- settings ---
    def _load_settings(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        for key, var in self._persisted.items():
            if key in data:
                try:
                    var.set(data[key])
                except tk.TclError:
                    pass

    def _save_settings(self):
        data = {key: var.get() for key, var in self._persisted.items()}
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError:
            pass

    def _on_close(self):
        # Stop the poll loop and cancel the pending after() callback *before*
        # destroying the window, so no scheduled callback fires post-destroy.
        self._closing = True
        self.cancel_event.set()
        if self._poll_id is not None:
            try:
                self.root.after_cancel(self._poll_id)
            except tk.TclError:
                pass
        self._save_settings()
        self.root.destroy()


def main():
    # Preflight: YouTube's JS challenge solver needs yt-dlp on Python >= 3.10.
    # If we were launched with an older/incapable interpreter, relaunch under a
    # capable one (guarded against loops) so the app "just works" regardless of
    # how it was started (terminal, IDE, double-click).
    if not (sys.version_info >= (3, 10) and ytdlp_supports_js_solver()):
        if not os.environ.get("VD_NO_RELAUNCH"):
            better = find_capable_python()
            if better and os.path.realpath(better) != os.path.realpath(sys.executable):
                print(f"[video_downloader] Relaunching under {better} "
                      "(current Python can't solve YouTube's JS challenge)...",
                      file=sys.stderr)
                env = dict(os.environ, VD_NO_RELAUNCH="1")
                try:
                    os.execve(better, [better, os.path.abspath(__file__)], env)
                except Exception as exc:  # noqa: BLE001 - fall through to current interp
                    print(f"[video_downloader] Relaunch failed ({exc}); "
                          "continuing on the current Python.", file=sys.stderr)

    root = tk.Tk()
    DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()