import json
import os
import shutil
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import pygame  # Musik
from PIL import Image, ImageTk  # Wallpaper-Thumbnails
import urllib.request
import urllib.error
import webbrowser
import zipfile
from datetime import datetime

APP_NAME = "LR Toolbox"
APP_VERSION = "0.1.0"

# Hier später deine echte Version-JSON-URL eintragen
REMOTE_VERSION_URL = "https://raw.githubusercontent.com/claratrash/LaRue_launcher/main/version.json"

BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
ASSETS_DIR = BASE_DIR / "assets"
MUSIC_DIR = ASSETS_DIR / "music"
WALLPAPER_DIR = ASSETS_DIR / "wallpapers"
LOGS_DIR = BASE_DIR / "logs"

USER_SETTINGS_FILE = CONFIG_DIR / "user_settings.json"
ANNOUNCEMENTS_FILE = CONFIG_DIR / "announcements.json"
FRONTEND_ASSET = ASSETS_DIR / "frontend.xml"
SERVICES_CHECK_BAT = ASSETS_DIR / "windows_service_check.bat"

# Fonts – überall Times New Roman Italic
FONT_TITLE = ("Times New Roman", 20, "italic")
FONT_H1 = ("Times New Roman", 14, "italic")
FONT_H2 = ("Times New Roman", 12, "italic")
FONT_TEXT = ("Times New Roman", 10, "italic")
FONT_BUTTON = ("Times New Roman", 12, "italic")

DEFAULT_SETTINGS = {
    "auto_clean_on_start": False,
    "auto_start_after_clean": False,
    "music": {"enabled": True, "volume": 0.2},  # 20 %
    "wqhd_minimap_enabled": False,
    "theme": "bw_neon",
    "fivem_path": None,
    "last_update_notified": ""
}


def ensure_dirs():
    """legt alle Standard-Ordner an"""
    for d in [CONFIG_DIR, ASSETS_DIR, MUSIC_DIR, WALLPAPER_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data):
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Konnte JSON {path} nicht speichern:", e)


def log_action(msg: str):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with (LOGS_DIR / "launcher.log").open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    except Exception:
        pass


def get_disk_usage(path: Path):
    try:
        total, used, free = shutil.disk_usage(str(path))
        used_pct = used / total * 100 if total else 0.0
        return total, used, free, used_pct
    except Exception:
        return None, None, None, None


class LRToolbox(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} – {APP_VERSION}")
        self.geometry("1200x750")
        self.configure(bg="#000000")
        self.resizable(True, True)

        ensure_dirs()

        # Settings laden oder Defaults schreiben
        if not USER_SETTINGS_FILE.exists():
            save_json(USER_SETTINGS_FILE, DEFAULT_SETTINGS)

        self.user_settings = load_json(USER_SETTINGS_FILE, DEFAULT_SETTINGS)

        # Musik-Einstellungen
        music_cfg = self.user_settings.get("music", {})
        self.music_enabled = bool(music_cfg.get("enabled", True))
        self.music_volume = float(music_cfg.get("volume", 0.2))
        self.music_available = False

        # FiveM-Root
        self.fivem_root = self.detect_fivem_root()

        # Status-Variablen (für Header)
        self.server_status_var = tk.StringVar(value="Status: unbekannt")
        self.players_var = tk.StringVar(value="Spieler: ?/?")

        # Announcements
        self.announcements = []
        self.current_announcement_index = 0
        self.ann_title_var = tk.StringVar(value="Keine Ankündigungen")
        self.ann_body_var = tk.StringVar(
            value="Lege Einträge in config/announcements.json an."
        )

        # Wallpaper-Thumbnails müssen referenziert bleiben
        self.wallpaper_images = []

        # Update-Status
        self.update_status_var = tk.StringVar(
            value=f"Lokale Version: {APP_VERSION} – kein Update-Check durchgeführt."
        )

        # Musik initialisieren
        self.init_music()

        # UI bauen
        self._build_ui()
        self.update_system_info()
        self.load_wallpapers()
        self.load_announcements()

        # Polls starten
        self.poll_server_status()
        self.start_announcement_rotation()

        # Auto-Update-Check einmal beim Start
        self.after(2000, self.auto_check_for_updates)

    # ---------- FiveM & System ----------
    def detect_fivem_root(self):
        """Versucht FiveM-Ordner zu finden."""
        stored = self.user_settings.get("fivem_path")
        if stored:
            p = Path(stored)
            if (p / "FiveM.app").exists() or (p / "FiveM.exe").exists():
                return p

        localapp = os.environ.get("LOCALAPPDATA")
        if localapp:
            cand1 = Path(localapp) / "FiveM" / "FiveM.app"
            if cand1.exists():
                self.user_settings["fivem_path"] = str(cand1.parent)
                save_json(USER_SETTINGS_FILE, self.user_settings)
                return cand1.parent

            cand2 = Path(localapp) / "FiveM"
            if cand2.exists():
                self.user_settings["fivem_path"] = str(cand2)
                save_json(USER_SETTINGS_FILE, self.user_settings)
                return cand2

        return None

    def ask_fivem_path(self):
        messagebox.showinfo(
            APP_NAME,
            "FiveM-Installation konnte nicht automatisch gefunden werden.\n"
            "Bitte wähle den Ordner, in dem sich FiveM befindet (Ordner mit FiveM.exe).",
        )
        path = filedialog.askdirectory(title="FiveM-Ordner auswählen")
        if not path:
            return
        p = Path(path)
        if not p.exists():
            messagebox.showerror(APP_NAME, "Der ausgewählte Pfad existiert nicht.")
            return
        self.user_settings["fivem_path"] = str(p)
        save_json(USER_SETTINGS_FILE, self.user_settings)
        self.fivem_root = self.detect_fivem_root()
        self.update_system_info()

    def ensure_fivem_root(self):
        if self.fivem_root and self.fivem_root.exists():
            return True
        self.ask_fivem_path()
        return bool(self.fivem_root and self.fivem_root.exists())

    def update_system_info(self):
        text_lines = []
        if self.fivem_root and self.fivem_root.exists():
            text_lines.append(f"FiveM gefunden unter:\n{self.fivem_root}")
            total, used, free, used_pct = get_disk_usage(self.fivem_root)
            if total:
                gb = 1024**3
                text_lines.append(f"Laufwerk: {self.fivem_root.drive}")
                text_lines.append(
                    f"Gesamt: {total/gb:.1f} GB, frei: {free/gb:.1f} GB ({100-used_pct:.1f}% frei)"
                )
                if used_pct > 85:
                    text_lines.append(
                        "WARNUNG: Laufwerk ist sehr voll (>85%). Das kann Performanceprobleme verursachen."
                    )
                elif used_pct > 80:
                    text_lines.append(
                        "Hinweis: Laufwerk ist >80% belegt. Mehr freier Speicher kann helfen."
                    )
            else:
                text_lines.append("Speicherinfo konnte nicht gelesen werden.")
        else:
            text_lines.append("FiveM-Installation wurde nicht automatisch gefunden.")
            text_lines.append("Du kannst den Pfad in den Einstellungen manuell auswählen.")

        self.system_text.configure(state="normal")
        self.system_text.delete("1.0", tk.END)
        self.system_text.insert("1.0", "\n".join(text_lines))
        self.system_text.configure(state="disabled")

    # ---------- Serverstatus ----------
    def poll_server_status(self):
        """
        Fragt direkt den FiveM-Server ab (info.json + players.json)
        und aktualisiert Status + Spielerzahl.
        """
        ip = "45.152.160.250"
        port = 30120

        status_text = "Status: OFFLINE"
        players_text = "Spieler: 0/?"

        try:
            with urllib.request.urlopen(
                f"http://{ip}:{port}/info.json", timeout=3
            ) as resp:
                info = json.loads(resp.read().decode("utf-8", errors="ignore"))

            with urllib.request.urlopen(
                f"http://{ip}:{port}/players.json", timeout=3
            ) as resp:
                players = json.loads(resp.read().decode("utf-8", errors="ignore"))

            player_count = len(players)
            max_players = None

            vars_section = info.get("vars", {})

            if "sv_maxClients" in vars_section:
                try:
                    max_players = int(vars_section["sv_maxClients"])
                except Exception:
                    max_players = None

            if max_players is None and "maxPlayers" in info:
                try:
                    max_players = int(info["maxPlayers"])
                except Exception:
                    max_players = None

            if max_players is None:
                max_players = player_count

            status_text = "Status: ONLINE"
            players_text = f"Spieler: {player_count}/{max_players}"

        except Exception:
            status_text = "Status: OFFLINE"
            players_text = "Spieler: 0/?"

        self.server_status_var.set(status_text)
        self.players_var.set(players_text)

        # Farben für Dot & Text je nach Status setzen
        try:
            if "ONLINE" in status_text:
                dot_color = "#00FFAA"   # kalt-neon grün
                text_color = "#FFFFFF"
            else:
                dot_color = "#FF5252"   # rot für offline
                text_color = "#AAAAAA"

            if hasattr(self, "status_dot"):
                self.status_dot.config(fg=dot_color)
            if hasattr(self, "status_label"):
                self.status_label.config(fg=text_color)
        except Exception:
            pass

        self.after(30000, self.poll_server_status)

    # ---------- Musik ----------
    def init_music(self):
        music_file = MUSIC_DIR / "music.mp3"
        if not music_file.exists():
            print("[INFO] music.mp3 nicht gefunden – Musik deaktiviert.")
            self.music_available = False
            return

        try:
            pygame.mixer.init()
            pygame.mixer.music.load(str(music_file))
            pygame.mixer.music.set_volume(self.music_volume)
            self.music_available = True
            if self.music_enabled:
                pygame.mixer.music.play(-1)
            print("[INFO] Musik initialisiert.")
        except Exception as e:
            print("[WARN] Konnte Musik nicht initialisieren:", e)
            self.music_available = False

    def update_music_state(self):
        if not self.music_available:
            return
        try:
            pygame.mixer.music.set_volume(self.music_volume)
            if self.music_enabled:
                if not pygame.mixer.music.get_busy():
                    pygame.mixer.music.play(-1)
            else:
                pygame.mixer.music.stop()
        except Exception as e:
            print("[WARN] Fehler beim Aktualisieren der Musik:", e)

    # ---------- Wallpaper ----------
    def load_wallpapers(self):
        for widget in self.wallpaper_list_frame.winfo_children():
            widget.destroy()
        self.wallpaper_images.clear()

        files = []
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
            files.extend(WALLPAPER_DIR.glob(ext))
        files = sorted(files)

        if not files:
            lbl = tk.Label(
                self.wallpaper_list_frame,
                text="Keine Wallpaper gefunden.\nLege Bilder in assets/wallpapers/ ab.",
                fg="#DDDDDD",
                bg="#111111",
                font=FONT_TEXT,
                justify="left",
            )
            lbl.pack(anchor="w", padx=5, pady=5)
            return

        max_width, max_height = 180, 120
        cols = 4
        row = 0
        col = 0

        for img_path in files:
            try:
                img = Image.open(img_path)
                img.thumbnail((max_width, max_height))
                tk_img = ImageTk.PhotoImage(img)
            except Exception as e:
                print(f"[WARN] Konnte Wallpaper {img_path} nicht laden: {e}")
                continue

            frame = tk.Frame(self.wallpaper_list_frame, bg="#111111", bd=1, relief=tk.RIDGE)
            frame.grid(row=row, column=col, padx=5, pady=5, sticky="n")

            label = tk.Label(frame, image=tk_img, bg="#111111")
            label.image = tk_img
            label.pack(padx=5, pady=5)

            name_label = tk.Label(
                frame,
                text=img_path.name,
                fg="#FFFFFF",
                bg="#111111",
                font=FONT_TEXT,
                wraplength=max_width,
            )
            name_label.pack(pady=(0, 5))

            btn = tk.Button(
                frame,
                text="Als Hintergrund setzen",
                bg="#222222",
                fg="#FFFFFF",
                activebackground="#333333",
                activeforeground="#FFFFFF",
                font=FONT_BUTTON,
                command=lambda p=img_path: self.set_wallpaper(p),
            )
            btn.pack(pady=(0, 5))

            self.wallpaper_images.append(tk_img)

            col += 1
            if col >= cols:
                col = 0
                row += 1

    def set_wallpaper(self, img_path: Path):
        try:
            import ctypes
            SPI_SETDESKWALLPAPER = 20
            r = ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETDESKWALLPAPER, 0, str(img_path), 3
            )
            if not r:
                raise RuntimeError("SystemParametersInfoW returned 0")
            messagebox.showinfo(APP_NAME, f"Wallpaper gesetzt:\n{img_path.name}")
            log_action(f"Wallpaper gesetzt: {img_path}")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Fehler beim Setzen des Wallpapers:\n{e}")

    # ---------- Announcements ----------
    def load_announcements(self):
        """Lädt Ankündigungen aus config/announcements.json, legt Default an wenn nötig."""
        if not ANNOUNCEMENTS_FILE.exists():
            default_data = {
                "announcements": [
                    {
                        "title": "Willkommen auf LaRueRP",
                        "body": "Verbinde dich direkt über den Launcher mit dem Server und tritt unserem Discord bei!"
                    },
                    {
                        "title": "Beispiel-Ankündigung",
                        "body": "Diese Nachrichten kommen aus config/announcements.json und können dort beliebig angepasst werden."
                    },
                ]
            }
            save_json(ANNOUNCEMENTS_FILE, default_data)
            data = default_data
        else:
            raw = load_json(ANNOUNCEMENTS_FILE, {"announcements": []})
            if isinstance(raw, list):
                data = {"announcements": raw}
            elif isinstance(raw, dict):
                data = raw
            else:
                data = {"announcements": []}

        self.announcements = data.get("announcements", []) or []
        self.current_announcement_index = 0
        self.show_announcement(0)

    def show_announcement(self, index=None):
        if not self.announcements:
            self.ann_title_var.set("Keine Ankündigungen")
            self.ann_body_var.set("Lege Einträge in config/announcements.json an.")
            return

        if index is None:
            index = self.current_announcement_index

        index = index % len(self.announcements)
        self.current_announcement_index = index
        ann = self.announcements[index]

        self.ann_title_var.set(ann.get("title", ""))
        self.ann_body_var.set(ann.get("body", ""))

    def next_announcement(self):
        if not self.announcements:
            return
        self.show_announcement(self.current_announcement_index + 1)

    def prev_announcement(self):
        if not self.announcements:
            return
        self.show_announcement(self.current_announcement_index - 1)

    def start_announcement_rotation(self):
        """Alle 15 Sekunden automatisch zur nächsten Anzeige springen."""
        def rotate():
            self.next_announcement()
            self.after(15000, rotate)

        self.after(15000, rotate)

    # ---------- UI ----------
    def _build_ui(self):
        header = tk.Frame(self, bg="#000000")
        header.pack(side=tk.TOP, fill=tk.X)

        title_label = tk.Label(
            header,
            text=APP_NAME,
            fg="#FFFFFF",
            bg="#000000",
            font=FONT_TITLE,
        )
        title_label.pack(side=tk.LEFT, padx=20, pady=10)

        status_frame = tk.Frame(header, bg="#000000")
        status_frame.pack(side=tk.RIGHT, padx=20)

        dot_and_text = tk.Frame(status_frame, bg="#000000")
        dot_and_text.pack(anchor="e")

        self.status_dot = tk.Label(
            dot_and_text,
            text="●",
            font=("Times New Roman", 18, "bold"),
            fg="#666666",
            bg="#000000",
        )
        self.status_dot.pack(side=tk.LEFT, padx=(0, 5))

        self.status_label = tk.Label(
            dot_and_text,
            textvariable=self.server_status_var,
            fg="#FFFFFF",
            bg="#000000",
            font=FONT_H2,
        )
        self.status_label.pack(side=tk.LEFT)

        self.players_label = tk.Label(
            status_frame,
            textvariable=self.players_var,
            fg="#AAAAAA",
            bg="#000000",
            font=FONT_TEXT,
        )
        self.players_label.pack(anchor="e")

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background="#000000", foreground="#FFFFFF")
        style.configure("TNotebook.Tab", padding=[10, 5])

        self.launcher_tab = tk.Frame(notebook, bg="#111111")
        self.visuals_tab = tk.Frame(notebook, bg="#111111")
        self.help_tab = tk.Frame(notebook, bg="#111111")
        self.settings_tab = tk.Frame(notebook, bg="#111111")
        self.info_tab = tk.Frame(notebook, bg="#111111")

        notebook.add(self.launcher_tab, text="Launcher")
        notebook.add(self.visuals_tab, text="Visuals")
        notebook.add(self.help_tab, text="Hilfe")
        notebook.add(self.settings_tab, text="Einstellungen")
        notebook.add(self.info_tab, text="Info & Update")

        self._build_launcher_tab()
        self._build_visuals_tab()
        self._build_help_tab()
        self._build_settings_tab()
        self._build_info_tab()

    # ---------- Launcher Tab ----------
    def _build_launcher_tab(self):
        left = tk.Frame(self.launcher_tab, bg="#111111")
        right = tk.Frame(self.launcher_tab, bg="#111111")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=20, pady=20)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(
            left, text="Aktionen", fg="#FFFFFF", bg="#111111", font=FONT_H1
        ).pack(anchor="w", pady=(0, 10))

        tk.Button(
            left,
            text="Schnell-Clean & Starten",
            font=FONT_BUTTON,
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            command=self.quick_clean_and_start,
        ).pack(fill=tk.X, pady=5)

        tk.Button(
            left,
            text="Vollständiger Clean",
            font=FONT_BUTTON,
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            command=self.full_clean,
        ).pack(fill=tk.X, pady=5)

        tk.Button(
            left,
            text="Nur LaRue starten",
            font=FONT_BUTTON,
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            command=self.start_larue_only,
        ).pack(fill=tk.X, pady=5)

        options_frame = tk.LabelFrame(
            left, text="Optionen", fg="#FFFFFF", bg="#111111", font=FONT_H2
        )
        options_frame.pack(fill=tk.X, pady=20)

        self.var_auto_start_after_clean = tk.BooleanVar(
            value=self.user_settings.get("auto_start_after_clean", False)
        )
        tk.Checkbutton(
            options_frame,
            text="Nach Clean automatisch LaRue starten",
            variable=self.var_auto_start_after_clean,
            fg="#FFFFFF",
            bg="#111111",
            selectcolor="#111111",
            activebackground="#111111",
            activeforeground="#FFFFFF",
            font=FONT_TEXT,
            command=self._save_settings,
        ).pack(anchor="w", pady=2)

        tk.Label(
            right,
            text="System / FiveM",
            fg="#FFFFFF",
            bg="#111111",
            font=FONT_H1,
        ).pack(anchor="w", pady=(0, 10))

        self.system_text = tk.Text(
            right, height=8, bg="#111111", fg="#DDDDDD", font=FONT_TEXT
        )
        self.system_text.pack(fill=tk.X, expand=False)

        sys_button_frame = tk.Frame(right, bg="#111111")
        sys_button_frame.pack(fill=tk.X, pady=(10, 5))

        tk.Button(
            sys_button_frame,
            text="Support-Log-Ordner öffnen",
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            font=FONT_BUTTON,
            command=lambda: self.open_folder(LOGS_DIR),
        ).pack(side=tk.LEFT, padx=(0, 5))

        tk.Button(
            sys_button_frame,
            text="FiveM Mods-/NVE-Ordner öffnen",
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            font=FONT_BUTTON,
            command=self.open_fivem_mods_folder,
        ).pack(side=tk.LEFT, padx=5)

        ann_frame = tk.LabelFrame(
            right,
            text="News / Ankündigungen",
            fg="#FFFFFF",
            bg="#111111",
            font=FONT_H2,
        )
        ann_frame.pack(fill=tk.BOTH, expand=True, pady=(15, 0))

        title_label = tk.Label(
            ann_frame,
            textvariable=self.ann_title_var,
            fg="#FFFFFF",
            bg="#111111",
            font=FONT_H1,
            anchor="w",
        )
        title_label.pack(fill=tk.X, padx=10, pady=(5, 2))

        body_label = tk.Label(
            ann_frame,
            textvariable=self.ann_body_var,
            fg="#DDDDDD",
            bg="#111111",
            font=FONT_TEXT,
            justify="left",
            wraplength=400,
            anchor="nw",
        )
        body_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

        nav_frame = tk.Frame(ann_frame, bg="#111111")
        nav_frame.pack(fill=tk.X, pady=5)

        tk.Button(
            nav_frame,
            text="<<",
            width=4,
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            font=FONT_BUTTON,
            command=self.prev_announcement,
        ).pack(side=tk.LEFT, padx=(10, 5))

        tk.Button(
            nav_frame,
            text=">>",
            width=4,
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            font=FONT_BUTTON,
            command=self.next_announcement,
        ).pack(side=tk.LEFT)

        link_frame = tk.Frame(self.launcher_tab, bg="#111111")
        link_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 10))

        tk.Label(
            link_frame,
            text="LaRue Links:",
            fg="#FFFFFF",
            bg="#111111",
            font=FONT_TEXT,
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(
            link_frame,
            text="Tebex-Shop",
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            font=FONT_BUTTON,
            command=lambda: self.open_url("https://la-rue-roleplay.tebex.io/"),
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            link_frame,
            text="Discord",
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            font=FONT_BUTTON,
            command=lambda: self.open_url("https://discord.gg/larue-rp"),
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            link_frame,
            text="TikTok",
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            font=FONT_BUTTON,
            command=lambda: self.open_url("https://www.tiktok.com/@larueroleplay"),
        ).pack(side=tk.LEFT, padx=5)

    # ---------- Visuals Tab ----------
    def _build_visuals_tab(self):
        top = tk.Frame(self.visuals_tab, bg="#111111")
        top.pack(fill=tk.X, padx=20, pady=10)

        tk.Label(
            top,
            text="Musik",
            fg="#FFFFFF",
            bg="#111111",
            font=FONT_H1,
        ).pack(anchor="w", pady=(0, 5))

        music_frame = tk.Frame(top, bg="#111111")
        music_frame.pack(anchor="w")

        self.var_music_enabled_ui = tk.BooleanVar(value=self.music_enabled)
        tk.Checkbutton(
            music_frame,
            text="Musik im Launcher abspielen",
            variable=self.var_music_enabled_ui,
            fg="#FFFFFF",
            bg="#111111",
            selectcolor="#111111",
            activebackground="#111111",
            activeforeground="#FFFFFF",
            font=FONT_TEXT,
            command=self._on_music_toggle,
        ).pack(anchor="w", pady=5)

        tk.Label(
            music_frame,
            text="Lautstärke",
            fg="#FFFFFF",
            bg="#111111",
            font=FONT_H2,
        ).pack(anchor="w", pady=(10, 0))

        self.volume_scale = tk.Scale(
            music_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            length=250,
            bg="#111111",
            fg="#FFFFFF",
            troughcolor="#222222",
            highlightthickness=0,
            command=self._on_volume_change,
            font=FONT_TEXT,
        )
        self.volume_scale.set(int(self.music_volume * 100))
        self.volume_scale.pack(anchor="w", pady=5)

        tk.Label(
            self.visuals_tab,
            text="Wallpapers",
            fg="#FFFFFF",
            bg="#111111",
            font=FONT_H1,
        ).pack(anchor="w", padx=20, pady=(10, 0))

        container = tk.Frame(self.visuals_tab, bg="#111111")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        canvas = tk.Canvas(container, bg="#111111", highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.wallpaper_list_frame = tk.Frame(canvas, bg="#111111")

        self.wallpaper_list_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas.create_window((0, 0), window=self.wallpaper_list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # ---------- Hilfe Tab ----------
    def _build_help_tab(self):
        tk.Label(
            self.help_tab,
            text="Hilfe / Infos",
            fg="#FFFFFF",
            bg="#111111",
            font=FONT_H1,
        ).pack(anchor="w", padx=20, pady=10)

        text = (
            "Hilfestellungen:\n\n"
            "• Game cache outdated → 'Vollständiger Clean' nutzen\n"
            "• Could not connect to server → Serverstatus prüfen, Internet prüfen\n"
            "• Crashes → Voll-Clean, SSD-Füllstand, Treiber prüfen\n"
            "• Minimap hängt → WQHD-Minimap-Option in den Einstellungen nutzen\n\n"
            "Vor Kontakt mit dem Support empfehlen wir:\n"
            "1. Windows Systemcheck ausführen\n"
            "2. Support-Paket (ZIP) erstellen und anhängen."
        )
        tk.Label(
            self.help_tab,
            text=text,
            justify="left",
            fg="#DDDDDD",
            bg="#111111",
            font=FONT_TEXT,
        ).pack(anchor="w", padx=20, pady=10)

        tk.Button(
            self.help_tab,
            text="Windows Systemcheck (Services, Firewall, Defender)",
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            font=FONT_BUTTON,
            command=self.run_services_check,
        ).pack(anchor="w", padx=20, pady=(10, 0))

        tk.Button(
            self.help_tab,
            text="Support-Paket erstellen (ZIP)",
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            font=FONT_BUTTON,
            command=self.export_support_bundle,
        ).pack(anchor="w", padx=20, pady=(10, 0))

    # ---------- Settings Tab ----------
    def _build_settings_tab(self):
        tk.Label(
            self.settings_tab,
            text="Einstellungen",
            fg="#FFFFFF",
            bg="#111111",
            font=FONT_H1,
        ).pack(anchor="w", padx=20, pady=10)

        frame = tk.Frame(self.settings_tab, bg="#111111")
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.var_wqhd = tk.BooleanVar(
            value=self.user_settings.get("wqhd_minimap_enabled", False)
        )
        tk.Checkbutton(
            frame,
            text="WQHD-Minimap aktivieren (frontend.xml ersetzen)",
            variable=self.var_wqhd,
            fg="#FFFFFF",
            bg="#111111",
            selectcolor="#111111",
            activebackground="#111111",
            activeforeground="#FFFFFF",
            font=FONT_TEXT,
            command=self.toggle_wqhd,
        ).pack(anchor="w", pady=5)

        tk.Button(
            frame,
            text="FiveM-Pfad manuell wählen...",
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            font=FONT_BUTTON,
            command=self.ask_fivem_path,
        ).pack(anchor="w", pady=15)

    # ---------- Info & Update Tab ----------
    def _build_info_tab(self):
        tk.Label(
            self.info_tab,
            text="LR Toolbox – Info & Updates",
            fg="#FFFFFF",
            bg="#111111",
            font=FONT_H1,
        ).pack(anchor="w", padx=20, pady=(10, 5))

        tk.Label(
            self.info_tab,
            text=f"Aktuelle Version: {APP_VERSION}",
            fg="#DDDDDD",
            bg="#111111",
            font=FONT_TEXT,
        ).pack(anchor="w", padx=20, pady=(0, 5))

        tk.Label(
            self.info_tab,
            text="Projekt / Repo (z. B. GitHub):",
            fg="#FFFFFF",
            bg="#111111",
            font=FONT_H2,
        ).pack(anchor="w", padx=20, pady=(15, 5))

        tk.Button(
            self.info_tab,
            text="Projektseite öffnen",
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            font=FONT_BUTTON,
            command=lambda: self.open_url("https://github.com/claratrash/LaRue_launcher"),
        ).pack(anchor="w", padx=20, pady=(0, 10))

        tk.Label(
            self.info_tab,
            text="Update-Status:",
            fg="#FFFFFF",
            bg="#111111",
            font=FONT_H2,
        ).pack(anchor="w", padx=20, pady=(10, 0))

        tk.Label(
            self.info_tab,
            textvariable=self.update_status_var,
            fg="#DDDDDD",
            bg="#111111",
            font=FONT_TEXT,
            wraplength=600,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(5, 10))

        tk.Button(
            self.info_tab,
            text="Nach Updates suchen",
            bg="#222222",
            fg="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
            font=FONT_BUTTON,
            command=self.check_for_updates,
        ).pack(anchor="w", padx=20, pady=(0, 5))

    # ---------- Aktionen ----------
    def quick_clean_and_start(self):
        if not self.ensure_fivem_root():
            return
        removed = self.clean_cache(full=False)
        log_action(f"Schnell-Clean durchgeführt, entfernte Einträge: {removed}")
        messagebox.showinfo(
            APP_NAME, f"Schnell-Clean abgeschlossen.\nEntfernte Einträge: {removed}"
        )
        if self.user_settings.get("auto_start_after_clean", False):
            self.start_larue_only()

    def full_clean(self):
        if not self.ensure_fivem_root():
            return
        removed = self.clean_cache(full=True)
        log_action(f"Vollständiger Clean durchgeführt, entfernte Einträge: {removed}")
        messagebox.showinfo(
            APP_NAME, f"Vollständiger Clean abgeschlossen.\nEntfernte Einträge: {removed}"
        )
        if self.user_settings.get("auto_start_after_clean", False):
            self.start_larue_only()

    def clean_cache(self, full: bool) -> int:
        """
        'Sicherer' Clean:
        - entfernt Crashes, Logs, reinen Game-/Server-Cache
        - lässt db/priv/browser/nui-storage in Ruhe (Logins & Einstellungen bleiben).
        """
        removed = 0
        root = self.fivem_root
        if root is None:
            return 0

        app_root = root / "FiveM.app"
        if app_root.exists():
            data = app_root / "data"
        else:
            app_root = root
            data = root / "data"

        candidates = [
            app_root / "crashes",
            app_root / "logs",
            data / "cache" / "files",
            data / "cache" / "game",
            data / "cache" / "servers",
            data / "cache" / "subprocess",
            data / "cache" / "unconfirmed",
        ]

        for path in candidates:
            if path.exists():
                for entry in path.rglob("*"):
                    try:
                        if entry.is_file() or entry.is_symlink():
                            entry.unlink(missing_ok=True)
                            removed += 1
                    except Exception:
                        pass
                for entry in sorted(path.glob("**/*"), reverse=True):
                    if entry.is_dir():
                        try:
                            entry.rmdir()
                            removed += 1
                        except OSError:
                            pass
        return removed

    def start_larue_only(self):
        """
        Startet LaRue über das offizielle FiveM-Protokoll.
        """
        connect_ip = "45.152.160.250:30120"
        url = f"fivem://connect/{connect_ip}"

        try:
            os.startfile(url)
            log_action(f"FiveM via URL gestartet: {url}")
        except OSError as e:
            messagebox.showerror(
                APP_NAME,
                "Konnte FiveM nicht über die fivem:// URL starten.\n"
                "Ist FiveM korrekt installiert und mit dem Protokoll verknüpft?\n\n"
                f"Fehler: {e}"
            )

    def toggle_wqhd(self):
        enabled = self.var_wqhd.get()
        self.user_settings["wqhd_minimap_enabled"] = enabled
        save_json(USER_SETTINGS_FILE, self.user_settings)

        if not self.ensure_fivem_root():
            return

        ui_dir = self.fivem_root / "FiveM.app" / "citizen" / "common" / "data" / "ui"
        if not ui_dir.exists():
            ui_dir = self.fivem_root / "citizen" / "common" / "data" / "ui"

        target = ui_dir / "frontend.xml"
        backup = ui_dir / "frontend.larue_backup.xml"

        if enabled:
            if not FRONTEND_ASSET.exists():
                messagebox.showerror(
                    APP_NAME,
                    "assets/frontend.xml wurde nicht gefunden.\n"
                    f"Erwartet unter:\n{FRONTEND_ASSET}",
                )
                return
            try:
                ui_dir.mkdir(parents=True, exist_ok=True)
                if target.exists() and not backup.exists():
                    shutil.copy2(target, backup)
                shutil.copy2(FRONTEND_ASSET, target)
                log_action(f"WQHD-Minimap aktiviert, frontend.xml ersetzt in {ui_dir}")
                messagebox.showinfo(
                    APP_NAME,
                    "WQHD-Minimap aktiviert.\nfrontend.xml wurde ersetzt.",
                )
            except Exception as e:
                messagebox.showerror(
                    APP_NAME, f"Fehler beim Ersetzen von frontend.xml: {e}"
                )
        else:
            try:
                if backup.exists():
                    shutil.copy2(backup, target)
                    log_action(
                        "WQHD-Minimap deaktiviert, Backup-frontend.xml wiederhergestellt."
                    )
                    messagebox.showinfo(
                        APP_NAME,
                        "WQHD-Minimap deaktiviert.\nBackup-frontend.xml wurde wiederhergestellt.",
                    )
                else:
                    messagebox.showwarning(
                        APP_NAME,
                        "Kein Backup von frontend.xml gefunden.\nEs wurde nichts geändert.",
                    )
            except Exception as e:
                messagebox.showerror(
                    APP_NAME, f"Fehler beim Wiederherstellen von frontend.xml: {e}"
                )

    # ---------- Helper / Links / Ordner / Update ----------
    def open_url(self, url: str):
        try:
            webbrowser.open(url, new=2)
            log_action(f"URL geöffnet: {url}")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Konnte die URL nicht öffnen:\n{e}")

    def open_folder(self, path: Path):
        try:
            if not path.exists():
                messagebox.showwarning(
                    APP_NAME,
                    f"Der Ordner existiert nicht:\n{path}"
                )
                return
            os.startfile(str(path))
            log_action(f"Ordner geöffnet: {path}")
        except Exception as e:
            messagebox.showerror(
                APP_NAME,
                f"Konnte den Ordner nicht öffnen:\n{e}"
            )

    def open_fivem_mods_folder(self):
        if not self.ensure_fivem_root():
            return

        root = self.fivem_root
        cand1 = root / "FiveM.app" / "mods"
        cand2 = root / "mods"

        if cand1.exists():
            target = cand1
        elif cand2.exists():
            target = cand2
        else:
            target = cand1
            target.mkdir(parents=True, exist_ok=True)

        self.open_folder(target)

    def run_services_check(self):
        if not SERVICES_CHECK_BAT.exists():
            messagebox.showerror(
                APP_NAME,
                f"Das Systemcheck-Skript wurde nicht gefunden.\n"
                f"Erwartet unter:\n{SERVICES_CHECK_BAT}"
            )
            return

        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", str(SERVICES_CHECK_BAT)],
                shell=True
            )
            log_action(f"Windows Services Check gestartet: {SERVICES_CHECK_BAT}")
        except Exception as e:
            messagebox.showerror(
                APP_NAME,
                f"Fehler beim Starten des Systemchecks:\n{e}"
            )

    def export_support_bundle(self):
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bundle_path = LOGS_DIR / f"lr_toolbox_support_{timestamp}.zip"

            with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
                log_file = LOGS_DIR / "launcher.log"
                if log_file.exists():
                    zf.write(log_file, arcname="launcher.log")

                if USER_SETTINGS_FILE.exists():
                    zf.write(USER_SETTINGS_FILE, arcname="config/user_settings.json")

                if ANNOUNCEMENTS_FILE.exists():
                    zf.write(ANNOUNCEMENTS_FILE, arcname="config/announcements.json")

                try:
                    sys_txt = self.system_text.get("1.0", tk.END).strip()
                    if sys_txt:
                        tmp_sys = LOGS_DIR / "systeminfo_from_launcher.txt"
                        tmp_sys.write_text(sys_txt, encoding="utf-8")
                        zf.write(tmp_sys, arcname="systeminfo_from_launcher.txt")
                        tmp_sys.unlink(missing_ok=True)
                except Exception:
                    pass

            log_action(f"Support-Bundle erstellt: {bundle_path}")
            messagebox.showinfo(
                APP_NAME,
                f"Support-Paket wurde erstellt:\n{bundle_path}\n\n"
                "Diese ZIP-Datei kannst du dem Support anhängen."
            )
        except Exception as e:
            messagebox.showerror(
                APP_NAME,
                f"Fehler beim Erstellen des Support-Pakets:\n{e}"
            )

    def parse_version(self, v: str):
        try:
            parts = v.strip().split(".")
            return tuple(int(p) for p in parts)
        except Exception:
            return (0,)

    def fetch_remote_version_info(self):
        """Holt die JSON-Daten von REMOTE_VERSION_URL und gibt (data, error) zurück."""
        if not REMOTE_VERSION_URL or not REMOTE_VERSION_URL.startswith("http"):
            return None, "REMOTE_VERSION_URL ist noch nicht konfiguriert."

        try:
            with urllib.request.urlopen(REMOTE_VERSION_URL, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            return data, None
        except Exception as e:
            return None, str(e)

    def check_for_updates(self):
        """Manueller Update-Check (über den Button im Info-Tab)."""
        self.update_status_var.set("Prüfe auf Updates...")
        data, error = self.fetch_remote_version_info()
        if error:
            self.update_status_var.set(f"Update-Check fehlgeschlagen: {error}")
            return

        remote_version = str(data.get("version", "")).strip()
        changelog = data.get("changelog", "")
        download_url = data.get("download_url", "")

        if not remote_version:
            self.update_status_var.set(
                "Antwort der Update-URL unvollständig (kein 'version'-Feld)."
            )
            return

        local_tuple = self.parse_version(APP_VERSION)
        remote_tuple = self.parse_version(remote_version)

        if remote_tuple > local_tuple:
            self.update_status_var.set(
                f"Neue Version verfügbar: {remote_version} (aktuell: {APP_VERSION})."
            )
            msg = f"Es ist eine neue Version verfügbar:\n\n" \
                  f"Aktuell: {APP_VERSION}\n" \
                  f"Neu:     {remote_version}\n\n"
            if changelog:
                msg += f"Changelog:\n{changelog}\n\n"
            if download_url:
                msg += "Möchtest du die Download-Seite jetzt öffnen?"
            else:
                msg += "Bitte besuche die Projektseite, um die neue Version herunterzuladen."

            if messagebox.askyesno(APP_NAME, msg):
                if download_url:
                    self.open_url(download_url)
                else:
                    self.open_url("https://github.com/claratrash/LaRue_launcher")

            # Merken, dass wir über diese Version informiert haben
            self.user_settings["last_update_notified"] = remote_version
            save_json(USER_SETTINGS_FILE, self.user_settings)
        else:
            self.update_status_var.set(
                f"Keine neuere Version gefunden. Du nutzt {APP_VERSION}."
            )

    def auto_check_for_updates(self):
        """
        Automatischer Update-Check beim Start.
        Fragt nur nach, wenn:
        - eine neue Version verfügbar ist UND
        - diese Version noch nicht als 'notified' gespeichert ist.
        """
        data, error = self.fetch_remote_version_info()
        if error or not data:
            # Kein Popup beim Auto-Check, nur leise im Status
            self.update_status_var.set(f"Auto-Update-Check fehlgeschlagen: {error}")
            return

        remote_version = str(data.get("version", "")).strip()
        changelog = data.get("changelog", "")
        download_url = data.get("download_url", "")

        if not remote_version:
            return

        local_tuple = self.parse_version(APP_VERSION)
        remote_tuple = self.parse_version(remote_version)

        last_notified = str(self.user_settings.get("last_update_notified", "")).strip()

        # Nur wenn Remote > Lokal und wir zu dieser Version noch nicht gefragt haben
        if remote_tuple > local_tuple and remote_version != last_notified:
            # Kleiner Hinweis unten im Info-Tab
            self.update_status_var.set(
                f"Neue Version verfügbar: {remote_version} (aktuell: {APP_VERSION})."
            )

            msg = f"Es ist eine neue Version der LR Toolbox verfügbar:\n\n" \
                  f"Aktuell: {APP_VERSION}\n" \
                  f"Neu:     {remote_version}\n\n"
            if changelog:
                msg += f"Changelog:\n{changelog}\n\n"
            if download_url:
                msg += "Möchtest du die Download-Seite jetzt öffnen?"
            else:
                msg += "Bitte besuche die Projektseite, um die neue Version herunterzuladen."

            if messagebox.askyesno(APP_NAME, msg):
                if download_url:
                    self.open_url(download_url)
                else:
                    self.open_url("https://github.com/claratrash/LaRue_launcher")

            # Egal ob Ja oder Nein → merken, dass wir diese Version gezeigt haben
            self.user_settings["last_update_notified"] = remote_version
            save_json(USER_SETTINGS_FILE, self.user_settings)


    # ---------- Musik-UI-Callbacks ----------
    def _on_music_toggle(self):
        self.music_enabled = self.var_music_enabled_ui.get()
        self.user_settings.setdefault("music", {})
        self.user_settings["music"]["enabled"] = self.music_enabled
        save_json(USER_SETTINGS_FILE, self.user_settings)
        self.update_music_state()

    def _on_volume_change(self, value):
        try:
            v = int(value)
        except ValueError:
            v = 20
        self.music_volume = max(0.0, min(1.0, v / 100.0))
        self.user_settings.setdefault("music", {})
        self.user_settings["music"]["volume"] = self.music_volume
        save_json(USER_SETTINGS_FILE, self.user_settings)
        self.update_music_state()

    # ---------- Settings speichern ----------
    def _save_settings(self):
        self.user_settings["auto_start_after_clean"] = self.var_auto_start_after_clean.get()
        save_json(USER_SETTINGS_FILE, self.user_settings)


if __name__ == "__main__":
    app = LRToolbox()
    app.mainloop()
