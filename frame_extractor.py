# frame_extractor.py
# source: github.com/zeittresor

import re
import time
import threading
import queue
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cv2


def sanitize_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[^\w\-. ]+", "_", name, flags=re.UNICODE)
    name = re.sub(r"\s+", "_", name)
    return name or "frames"


class ToolTip:
    """
    Tooltip that stands out: border + slightly darker background.
    Uses plain tk widgets for consistent styling across ttk themes.
    """

    def __init__(
        self,
        widget: tk.Widget,
        get_text_func,
        delay_ms: int = 450,
        wraplength: int = 420,
        bg: str = "#E3E3E3",
        border_color: str = "#404040",
        border_width: int = 1,
        padding: tuple[int, int] = (10, 6),
    ):
        self.widget = widget
        self.get_text = get_text_func
        self.delay_ms = delay_ms
        self.wraplength = wraplength

        self.bg = bg
        self.border_color = border_color
        self.border_width = border_width
        self.padding = padding

        self._after_id = None
        self._tip = None

        widget.bind("<Enter>", self._on_enter, add=True)
        widget.bind("<Leave>", self._on_leave, add=True)
        widget.bind("<ButtonPress>", self._on_leave, add=True)

    def _on_enter(self, _event=None):
        self._schedule()

    def _on_leave(self, _event=None):
        self._unschedule()
        self._hide()

    def _schedule(self):
        self._unschedule()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _unschedule(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self):
        text = (self.get_text() or "").strip()
        if not text:
            return

        if self._tip is not None:
            self._hide()

        try:
            x = self.widget.winfo_rootx() + 10
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        except tk.TclError:
            return

        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")

        outer = tk.Frame(self._tip, bg=self.border_color, bd=0, highlightthickness=0)
        outer.pack(fill="both", expand=True)

        inner = tk.Frame(outer, bg=self.bg, bd=0, highlightthickness=0)
        inner.pack(
            padx=self.border_width,
            pady=self.border_width,
            fill="both",
            expand=True,
        )

        lbl = tk.Label(
            inner,
            text=text,
            bg=self.bg,
            fg="#000000",
            justify="left",
            wraplength=self.wraplength,
            padx=self.padding[0],
            pady=self.padding[1],
        )
        lbl.pack()

    def _hide(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


@dataclass
class ExtractConfig:
    input_path: Path
    output_root: Path
    create_subfolder: bool
    subfolder_name: str
    mode: str  # "all" | "every_n" | "target_fps"
    every_n: int
    target_fps: float
    start_sec: float
    end_sec: float  # <= 0 means "until end"
    resize_mode: str  # "none" | "max_width" | "max_height" | "fit_box"
    max_width: int
    max_height: int
    format: str  # "png" | "jpg" | "webp"
    quality: int  # 1..100 used for jpg/webp
    digits: int
    overwrite: bool
    skip_existing: bool


I18N = {
    "en": {
        "app_title": "MP4 → Frames (Frame Extractor)",
        "group_io": "Files & Output",
        "group_options": "Options",
        "group_log": "Log",
        "lbl_language": "Language:",
        "lang_en": "English",
        "lang_de": "Deutsch",
        "lang_fr": "Français",
        "lbl_input": "MP4 file:",
        "lbl_output": "Output folder:",
        "btn_browse": "Browse…",
        "btn_folder": "Folder…",
        "chk_subfolder": "Create subfolder",
        "lbl_subfolder_name": "Name:",
        "lbl_extraction": "Extraction:",
        "rb_all": "All frames",
        "rb_every_n": "Every Nth frame",
        "rb_target_fps": "Target FPS",
        "lbl_n": "N:",
        "lbl_target_fps": "Target FPS:",
        "lbl_start_sec": "Start (sec):",
        "lbl_end_sec": "End (sec, 0=to end):",
        "lbl_resize": "Resize:",
        "lbl_max_w": "Max W:",
        "lbl_max_h": "Max H:",
        "lbl_format": "Format:",
        "lbl_quality": "Quality (JPG/WEBP):",
        "lbl_digits": "Digits (padding):",
        "chk_overwrite": "Overwrite existing files",
        "chk_skip": "Skip existing files",
        "btn_start": "Start",
        "btn_stop": "Stop",
        "status_ready": "Ready.",
        "status_starting": "Starting…",
        "status_stop_requested": "Stop requested…",
        "log_input": "Input:  {path}",
        "log_output": "Output: {path}",
        "log_sep": "—" * 60,
        "dlg_error_title": "Error",
        "dlg_done_title": "Done",
        "err_invalid_video": "Please select a valid video file.",
        "err_invalid_output": "Please select a valid output folder.",
        "err_targetfps_invalid": "Target FPS must be > 0.",
        "err_invalid_format": "Invalid output format.",
        "err_open_failed": "Could not open the video (codec/file?).",
        "done_msg": "Extraction finished.\nSaved frames: {count}\n\nOutput:\n{out_dir}",
        "status_progress_eta": "Processed: {scanned}/{total} | Saved (index): {saved}{eta}",
        "status_progress_unknown": "Processed: {scanned} | Saved (index): {saved} | Runtime: {secs}s",
        "eta_fmt": " | ETA ~ {secs}s",
        "fdlg_pick_video": "Select video file",
        "fdlg_pick_folder": "Select output folder",
        "ft_mp4": "MP4 video",
        "ft_video": "Video",
        "ft_all": "All files",
        "tip_language": "Switch the language used for dialogs and tooltips.",
        "tip_input": "Select an input video (MP4 recommended).",
        "tip_output": "Select where the extracted images should be saved.",
        "tip_subfolder": "If enabled, frames will be saved into a subfolder inside the output folder.",
        "tip_mode": "Choose how densely frames are extracted (all, every Nth, or by target FPS).",
        "tip_every_n": "When enabled: keep every Nth frame (e.g. N=10 keeps 0,10,20,…).",
        "tip_target_fps": "When enabled: approximate the given frames-per-second rate (downsampling).",
        "tip_timerange": "Optionally limit extraction to a time window. End=0 means to the end.",
        "tip_resize": "Optionally resize frames to reduce disk usage (keeps aspect ratio).",
        "tip_format": "PNG is lossless. JPG/WEBP are smaller but can lose quality.",
        "tip_quality": "Applies to JPG/WEBP only (higher = better quality, larger files).",
        "tip_digits": "Number of digits used for filenames (e.g. 000001).",
        "tip_overwrite": "If enabled, existing files with the same name will be overwritten.",
        "tip_skip": "If enabled, existing files will be kept and not written again.",
        "tip_start_btn": "Start extracting frames with the selected settings.",
        "tip_stop_btn": "Request cancellation (stops after the current frame).",
    },
    "de": {
        "app_title": "MP4 → Einzelbilder (Frame Extractor)",
        "group_io": "Dateien & Zielordner",
        "group_options": "Optionen",
        "group_log": "Log",
        "lbl_language": "Sprache:",
        "lang_en": "English",
        "lang_de": "Deutsch",
        "lang_fr": "Français",
        "lbl_input": "MP4 Datei:",
        "lbl_output": "Output Ordner:",
        "btn_browse": "Auswählen…",
        "btn_folder": "Ordner…",
        "chk_subfolder": "Unterordner erstellen",
        "lbl_subfolder_name": "Name:",
        "lbl_extraction": "Extraktion:",
        "rb_all": "Alle Frames",
        "rb_every_n": "Jeden N-ten Frame",
        "rb_target_fps": "Ziel-FPS",
        "lbl_n": "N:",
        "lbl_target_fps": "Ziel-FPS:",
        "lbl_start_sec": "Start (Sek):",
        "lbl_end_sec": "Ende (Sek, 0=bis Ende):",
        "lbl_resize": "Resize:",
        "lbl_max_w": "Max W:",
        "lbl_max_h": "Max H:",
        "lbl_format": "Format:",
        "lbl_quality": "Qualität (JPG/WEBP):",
        "lbl_digits": "Ziffern (Padding):",
        "chk_overwrite": "Vorhandene Dateien überschreiben",
        "chk_skip": "Vorhandene Dateien überspringen",
        "btn_start": "Start",
        "btn_stop": "Stop",
        "status_ready": "Bereit.",
        "status_starting": "Starte…",
        "status_stop_requested": "Stop angefordert…",
        "log_input": "Input:  {path}",
        "log_output": "Output: {path}",
        "log_sep": "—" * 60,
        "dlg_error_title": "Fehler",
        "dlg_done_title": "Fertig",
        "err_invalid_video": "Bitte eine gültige Video-Datei auswählen.",
        "err_invalid_output": "Bitte einen gültigen Output-Ordner wählen.",
        "err_targetfps_invalid": "Ziel-FPS muss > 0 sein.",
        "err_invalid_format": "Ungültiges Ausgabeformat.",
        "err_open_failed": "Video konnte nicht geöffnet werden (Codec/Datei?).",
        "done_msg": "Extraktion abgeschlossen.\nGespeicherte Frames: {count}\n\nOutput:\n{out_dir}",
        "status_progress_eta": "Verarbeitet: {scanned}/{total} | Gespeichert (Index): {saved}{eta}",
        "status_progress_unknown": "Verarbeitet: {scanned} | Gespeichert (Index): {saved} | Laufzeit: {secs}s",
        "eta_fmt": " | ETA ~ {secs}s",
        "fdlg_pick_video": "Video auswählen",
        "fdlg_pick_folder": "Output-Ordner wählen",
        "ft_mp4": "MP4 Video",
        "ft_video": "Video",
        "ft_all": "Alle Dateien",
        "tip_language": "Wechselt die Sprache für Dialoge und Tooltips.",
        "tip_input": "Wähle ein Input-Video (MP4 empfohlen).",
        "tip_output": "Wähle, wo die extrahierten Bilder gespeichert werden sollen.",
        "tip_subfolder": "Wenn aktiv, werden die Frames in einem Unterordner im Output gespeichert.",
        "tip_mode": "Wähle die Extraktionsdichte (alle Frames, jeden N-ten oder per Ziel-FPS).",
        "tip_every_n": "Wenn aktiv: jeden N-ten Frame speichern (z.B. N=10 -> 0,10,20,…).",
        "tip_target_fps": "Wenn aktiv: ungefähr mit der angegebenen Bildrate extrahieren (Downsampling).",
        "tip_timerange": "Optional die Extraktion auf einen Zeitbereich begrenzen. Ende=0 bedeutet bis zum Ende.",
        "tip_resize": "Optional Frames verkleinern, um Speicherplatz zu sparen (Seitenverhältnis bleibt).",
        "tip_format": "PNG ist verlustfrei. JPG/WEBP sind kleiner, aber ggf. mit Qualitätsverlust.",
        "tip_quality": "Nur für JPG/WEBP (höher = bessere Qualität, größere Dateien).",
        "tip_digits": "Anzahl Ziffern im Dateinamen (z.B. 000001).",
        "tip_overwrite": "Wenn aktiv, werden vorhandene Dateien gleichen Namens überschrieben.",
        "tip_skip": "Wenn aktiv, werden vorhandene Dateien nicht erneut geschrieben.",
        "tip_start_btn": "Startet die Extraktion mit den gewählten Einstellungen.",
        "tip_stop_btn": "Bricht ab (Stop nach dem aktuellen Frame).",
    },
    "fr": {
        "app_title": "MP4 → Images (Frame Extractor)",
        "group_io": "Fichiers & Sortie",
        "group_options": "Options",
        "group_log": "Journal",
        "lbl_language": "Langue :",
        "lang_en": "English",
        "lang_de": "Deutsch",
        "lang_fr": "Français",
        "lbl_input": "Fichier MP4 :",
        "lbl_output": "Dossier de sortie :",
        "btn_browse": "Parcourir…",
        "btn_folder": "Dossier…",
        "chk_subfolder": "Créer un sous-dossier",
        "lbl_subfolder_name": "Nom :",
        "lbl_extraction": "Extraction :",
        "rb_all": "Toutes les images",
        "rb_every_n": "Chaque Nᵉ image",
        "rb_target_fps": "FPS cible",
        "lbl_n": "N :",
        "lbl_target_fps": "FPS cible :",
        "lbl_start_sec": "Début (s) :",
        "lbl_end_sec": "Fin (s, 0=jusqu'à la fin) :",
        "lbl_resize": "Redimensionnement :",
        "lbl_max_w": "Largeur max :",
        "lbl_max_h": "Hauteur max :",
        "lbl_format": "Format :",
        "lbl_quality": "Qualité (JPG/WEBP) :",
        "lbl_digits": "Chiffres (padding) :",
        "chk_overwrite": "Écraser les fichiers existants",
        "chk_skip": "Ignorer les fichiers existants",
        "btn_start": "Démarrer",
        "btn_stop": "Arrêter",
        "status_ready": "Prêt.",
        "status_starting": "Démarrage…",
        "status_stop_requested": "Arrêt demandé…",
        "log_input": "Entrée :  {path}",
        "log_output": "Sortie : {path}",
        "log_sep": "—" * 60,
        "dlg_error_title": "Erreur",
        "dlg_done_title": "Terminé",
        "err_invalid_video": "Veuillez sélectionner un fichier vidéo valide.",
        "err_invalid_output": "Veuillez sélectionner un dossier de sortie valide.",
        "err_targetfps_invalid": "Le FPS cible doit être > 0.",
        "err_invalid_format": "Format de sortie invalide.",
        "err_open_failed": "Impossible d'ouvrir la vidéo (codec/fichier ?).",
        "done_msg": "Extraction terminée.\nImages enregistrées : {count}\n\nSortie :\n{out_dir}",
        "status_progress_eta": "Traitement : {scanned}/{total} | Enregistré (index) : {saved}{eta}",
        "status_progress_unknown": "Traitement : {scanned} | Enregistré (index) : {saved} | Durée : {secs}s",
        "eta_fmt": " | ETA ~ {secs}s",
        "fdlg_pick_video": "Sélectionner une vidéo",
        "fdlg_pick_folder": "Sélectionner le dossier de sortie",
        "ft_mp4": "Vidéo MP4",
        "ft_video": "Vidéo",
        "ft_all": "Tous les fichiers",
        "tip_language": "Changer la langue des dialogues et des info-bulles.",
        "tip_input": "Sélectionnez une vidéo d'entrée (MP4 recommandé).",
        "tip_output": "Choisissez où enregistrer les images extraites.",
        "tip_subfolder": "Si activé, les images seront enregistrées dans un sous-dossier du dossier de sortie.",
        "tip_mode": "Choisissez la densité d'extraction (toutes, chaque Nᵉ, ou FPS cible).",
        "tip_every_n": "Si activé : conserver chaque Nᵉ image (ex. N=10 -> 0,10,20,…).",
        "tip_target_fps": "Si activé : approximer le nombre d'images par seconde (échantillonnage).",
        "tip_timerange": "Limiter l'extraction à une plage de temps. Fin=0 signifie jusqu'à la fin.",
        "tip_resize": "Redimensionner pour réduire l'espace disque (conserve le ratio).",
        "tip_format": "PNG est sans perte. JPG/WEBP sont plus petits mais peuvent perdre en qualité.",
        "tip_quality": "Pour JPG/WEBP uniquement (plus haut = meilleure qualité, fichiers plus gros).",
        "tip_digits": "Nombre de chiffres dans le nom (ex. 000001).",
        "tip_overwrite": "Si activé, les fichiers existants seront remplacés.",
        "tip_skip": "Si activé, les fichiers existants seront conservés.",
        "tip_start_btn": "Démarrer l'extraction avec ces paramètres.",
        "tip_stop_btn": "Demander l'annulation (arrêt après l'image en cours).",
    },
}


class FrameExtractorGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.q = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None

        self.lang_var = tk.StringVar(value="en")
        self._i18n_bindings = []  # (widget, option, key)
        self._tooltips = []

        self._build_ui()
        self.apply_language()
        self._poll_queue()

    def tr(self, key: str, **kwargs) -> str:
        lang = self.lang_var.get() or "en"
        base = I18N.get(lang, {})
        text = base.get(key) or I18N["en"].get(key) or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def bind_i18n(self, widget, option: str, key: str):
        self._i18n_bindings.append((widget, option, key))

    def add_tooltip(self, widget, key: str):
        tip = ToolTip(widget, lambda k=key: self.tr(k))
        self._tooltips.append(tip)

    def apply_language(self):
        self.title(self.tr("app_title"))
        for widget, option, key in self._i18n_bindings:
            try:
                widget.configure(**{option: self.tr(key)})
            except tk.TclError:
                pass
        self.status_var.set(self.tr("status_ready"))

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.geometry("860x600")
        self.minsize(820, 560)

        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        # Top bar: language
        top = ttk.Frame(root)
        top.pack(fill="x", pady=(0, 10))

        lbl_lang = ttk.Label(top)
        lbl_lang.pack(side="left")
        self.bind_i18n(lbl_lang, "text", "lbl_language")

        rb_en = ttk.Radiobutton(top, variable=self.lang_var, value="en", command=self.apply_language)
        rb_de = ttk.Radiobutton(top, variable=self.lang_var, value="de", command=self.apply_language)
        rb_fr = ttk.Radiobutton(top, variable=self.lang_var, value="fr", command=self.apply_language)
        rb_en.pack(side="left", padx=(10, 0))
        rb_de.pack(side="left", padx=(10, 0))
        rb_fr.pack(side="left", padx=(10, 0))
        self.bind_i18n(rb_en, "text", "lang_en")
        self.bind_i18n(rb_de, "text", "lang_de")
        self.bind_i18n(rb_fr, "text", "lang_fr")
        self.add_tooltip(lbl_lang, "tip_language")

        # --- Input / Output ---
        io = ttk.LabelFrame(root, padding=10)
        io.pack(fill="x", pady=(0, 10))
        self.bind_i18n(io, "text", "group_io")

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar(value=str(Path.cwd()))

        lbl_in = ttk.Label(io)
        lbl_in.grid(row=0, column=0, sticky="w")
        self.bind_i18n(lbl_in, "text", "lbl_input")

        in_entry = ttk.Entry(io, textvariable=self.in_var)
        in_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))

        btn_browse = ttk.Button(io, command=self.pick_input)
        btn_browse.grid(row=0, column=2)
        self.bind_i18n(btn_browse, "text", "btn_browse")

        lbl_out = ttk.Label(io)
        lbl_out.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.bind_i18n(lbl_out, "text", "lbl_output")

        out_entry = ttk.Entry(io, textvariable=self.out_var)
        out_entry.grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))

        btn_folder = ttk.Button(io, command=self.pick_output)
        btn_folder.grid(row=1, column=2, pady=(8, 0))
        self.bind_i18n(btn_folder, "text", "btn_folder")

        io.columnconfigure(1, weight=1)

        self.create_subfolder_var = tk.BooleanVar(value=True)
        self.subfolder_var = tk.StringVar(value="video_frames")

        subrow = ttk.Frame(io)
        subrow.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        chk_sub = ttk.Checkbutton(subrow, variable=self.create_subfolder_var, command=self._update_subfolder_state)
        chk_sub.pack(side="left")
        self.bind_i18n(chk_sub, "text", "chk_subfolder")

        lbl_subname = ttk.Label(subrow)
        lbl_subname.pack(side="left", padx=(12, 6))
        self.bind_i18n(lbl_subname, "text", "lbl_subfolder_name")

        self.subfolder_entry = ttk.Entry(subrow, textvariable=self.subfolder_var, width=30)
        self.subfolder_entry.pack(side="left", fill="x", expand=True)

        self.add_tooltip(in_entry, "tip_input")
        self.add_tooltip(btn_browse, "tip_input")
        self.add_tooltip(out_entry, "tip_output")
        self.add_tooltip(btn_folder, "tip_output")
        self.add_tooltip(chk_sub, "tip_subfolder")
        self.add_tooltip(self.subfolder_entry, "tip_subfolder")

        # --- Options ---
        opts = ttk.LabelFrame(root, padding=10)
        opts.pack(fill="x", pady=(0, 10))
        self.bind_i18n(opts, "text", "group_options")

        self.mode_var = tk.StringVar(value="all")
        mode_row = ttk.Frame(opts)
        mode_row.pack(fill="x")

        lbl_mode = ttk.Label(mode_row)
        lbl_mode.pack(side="left")
        self.bind_i18n(lbl_mode, "text", "lbl_extraction")

        rb_all = ttk.Radiobutton(mode_row, value="all", variable=self.mode_var, command=self._update_mode_state)
        rb_all.pack(side="left", padx=(10, 0))
        self.bind_i18n(rb_all, "text", "rb_all")

        rb_every = ttk.Radiobutton(mode_row, value="every_n", variable=self.mode_var, command=self._update_mode_state)
        rb_every.pack(side="left", padx=(10, 0))
        self.bind_i18n(rb_every, "text", "rb_every_n")

        rb_tfps = ttk.Radiobutton(mode_row, value="target_fps", variable=self.mode_var, command=self._update_mode_state)
        rb_tfps.pack(side="left", padx=(10, 0))
        self.bind_i18n(rb_tfps, "text", "rb_target_fps")

        self.add_tooltip(mode_row, "tip_mode")

        self.every_n_var = tk.IntVar(value=1)
        self.target_fps_var = tk.DoubleVar(value=5.0)

        mode_row2 = ttk.Frame(opts)
        mode_row2.pack(fill="x", pady=(6, 0))

        lbl_n = ttk.Label(mode_row2)
        lbl_n.pack(side="left")
        self.bind_i18n(lbl_n, "text", "lbl_n")

        self.every_n_spin = ttk.Spinbox(mode_row2, from_=1, to=9999, textvariable=self.every_n_var, width=8)
        self.every_n_spin.pack(side="left", padx=(6, 18))

        lbl_tfps = ttk.Label(mode_row2)
        lbl_tfps.pack(side="left")
        self.bind_i18n(lbl_tfps, "text", "lbl_target_fps")

        self.target_fps_spin = ttk.Spinbox(
            mode_row2, from_=0.1, to=240.0, increment=0.5, textvariable=self.target_fps_var, width=8
        )
        self.target_fps_spin.pack(side="left", padx=(6, 0))

        self.add_tooltip(self.every_n_spin, "tip_every_n")
        self.add_tooltip(self.target_fps_spin, "tip_target_fps")

        # Time range
        trw = ttk.Frame(opts)
        trw.pack(fill="x", pady=(10, 0))
        self.start_var = tk.DoubleVar(value=0.0)
        self.end_var = tk.DoubleVar(value=0.0)

        lbl_start = ttk.Label(trw)
        lbl_start.pack(side="left")
        self.bind_i18n(lbl_start, "text", "lbl_start_sec")
        ttk.Entry(trw, textvariable=self.start_var, width=10).pack(side="left", padx=(6, 18))

        lbl_end = ttk.Label(trw)
        lbl_end.pack(side="left")
        self.bind_i18n(lbl_end, "text", "lbl_end_sec")
        ttk.Entry(trw, textvariable=self.end_var, width=10).pack(side="left", padx=(6, 0))

        self.add_tooltip(trw, "tip_timerange")

        # Resize
        rz = ttk.Frame(opts)
        rz.pack(fill="x", pady=(10, 0))
        self.resize_mode_var = tk.StringVar(value="none")

        lbl_resize = ttk.Label(rz)
        lbl_resize.pack(side="left")
        self.bind_i18n(lbl_resize, "text", "lbl_resize")

        self.resize_combo = ttk.Combobox(
            rz, textvariable=self.resize_mode_var, state="readonly", width=14, values=("none", "max_width", "max_height", "fit_box")
        )
        self.resize_combo.pack(side="left", padx=(6, 12))

        self.max_w_var = tk.IntVar(value=1280)
        self.max_h_var = tk.IntVar(value=720)

        lbl_mw = ttk.Label(rz)
        lbl_mw.pack(side="left")
        self.bind_i18n(lbl_mw, "text", "lbl_max_w")
        ttk.Spinbox(rz, from_=1, to=99999, textvariable=self.max_w_var, width=8).pack(side="left", padx=(6, 18))

        lbl_mh = ttk.Label(rz)
        lbl_mh.pack(side="left")
        self.bind_i18n(lbl_mh, "text", "lbl_max_h")
        ttk.Spinbox(rz, from_=1, to=99999, textvariable=self.max_h_var, width=8).pack(side="left", padx=(6, 0))

        self.add_tooltip(rz, "tip_resize")

        # Output format
        of = ttk.Frame(opts)
        of.pack(fill="x", pady=(10, 0))

        self.format_var = tk.StringVar(value="png")
        self.quality_var = tk.IntVar(value=92)
        self.digits_var = tk.IntVar(value=6)

        lbl_fmt = ttk.Label(of)
        lbl_fmt.pack(side="left")
        self.bind_i18n(lbl_fmt, "text", "lbl_format")

        fmt = ttk.Combobox(of, textvariable=self.format_var, state="readonly", width=8, values=("png", "jpg", "webp"))
        fmt.pack(side="left", padx=(6, 18))

        lbl_q = ttk.Label(of)
        lbl_q.pack(side="left")
        self.bind_i18n(lbl_q, "text", "lbl_quality")
        sp_q = ttk.Spinbox(of, from_=1, to=100, textvariable=self.quality_var, width=6)
        sp_q.pack(side="left", padx=(6, 18))

        lbl_d = ttk.Label(of)
        lbl_d.pack(side="left")
        self.bind_i18n(lbl_d, "text", "lbl_digits")
        sp_d = ttk.Spinbox(of, from_=3, to=12, textvariable=self.digits_var, width=6)
        sp_d.pack(side="left", padx=(6, 0))

        self.add_tooltip(fmt, "tip_format")
        self.add_tooltip(sp_q, "tip_quality")
        self.add_tooltip(sp_d, "tip_digits")

        # Overwrite/skip
        sw = ttk.Frame(opts)
        sw.pack(fill="x", pady=(10, 0))

        self.overwrite_var = tk.BooleanVar(value=False)
        self.skip_existing_var = tk.BooleanVar(value=True)

        chk_ow = ttk.Checkbutton(sw, variable=self.overwrite_var, command=self._coerce_overwrite_skip)
        chk_ow.pack(side="left")
        self.bind_i18n(chk_ow, "text", "chk_overwrite")

        chk_sk = ttk.Checkbutton(sw, variable=self.skip_existing_var, command=self._coerce_overwrite_skip)
        chk_sk.pack(side="left", padx=(14, 0))
        self.bind_i18n(chk_sk, "text", "chk_skip")

        self.add_tooltip(chk_ow, "tip_overwrite")
        self.add_tooltip(chk_sk, "tip_skip")

        # --- Progress / Controls ---
        bottom = ttk.Frame(root)
        bottom.pack(fill="x", pady=(0, 10))

        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(fill="x")

        self.status_var = tk.StringVar(value=self.tr("status_ready"))
        ttk.Label(bottom, textvariable=self.status_var).pack(anchor="w", pady=(6, 0))

        btns = ttk.Frame(root)
        btns.pack(fill="x")

        self.start_btn = ttk.Button(btns, command=self.start_extract)
        self.stop_btn = ttk.Button(btns, command=self.stop_extract, state="disabled")
        self.start_btn.pack(side="left")
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.bind_i18n(self.start_btn, "text", "btn_start")
        self.bind_i18n(self.stop_btn, "text", "btn_stop")
        self.add_tooltip(self.start_btn, "tip_start_btn")
        self.add_tooltip(self.stop_btn, "tip_stop_btn")

        # --- Log ---
        logf = ttk.LabelFrame(root, padding=10)
        logf.pack(fill="both", expand=True, pady=(10, 0))
        self.bind_i18n(logf, "text", "group_log")

        self.log = tk.Text(logf, height=12, wrap="word")
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

        self._update_mode_state()
        self._update_subfolder_state()
        self._coerce_overwrite_skip()

    def _update_subfolder_state(self):
        st = "normal" if self.create_subfolder_var.get() else "disabled"
        self.subfolder_entry.configure(state=st)

    def _coerce_overwrite_skip(self):
        if self.overwrite_var.get() and self.skip_existing_var.get():
            self.skip_existing_var.set(False)

    def _update_mode_state(self):
        mode = self.mode_var.get()
        self.every_n_spin.configure(state=("normal" if mode == "every_n" else "disabled"))
        self.target_fps_spin.configure(state=("normal" if mode == "target_fps" else "disabled"))

    def append_log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def pick_input(self):
        p = filedialog.askopenfilename(
            title=self.tr("fdlg_pick_video"),
            filetypes=[
                (self.tr("ft_mp4"), "*.mp4"),
                (self.tr("ft_video"), "*.mp4;*.mkv;*.mov;*.avi"),
                (self.tr("ft_all"), "*.*"),
            ],
        )
        if p:
            self.in_var.set(p)
            stem = Path(p).stem
            ts = time.strftime("%Y%m%d_%H%M%S")
            self.subfolder_var.set(sanitize_name(f"{stem}_frames_{ts}"))

    def pick_output(self):
        p = filedialog.askdirectory(title=self.tr("fdlg_pick_folder"))
        if p:
            self.out_var.set(p)

    def _make_config(self) -> ExtractConfig | None:
        in_path = Path(self.in_var.get().strip('" ').strip())
        out_root = Path(self.out_var.get().strip('" ').strip())

        if not in_path.is_file():
            messagebox.showerror(self.tr("dlg_error_title"), self.tr("err_invalid_video"))
            return None
        if not out_root.exists() or not out_root.is_dir():
            messagebox.showerror(self.tr("dlg_error_title"), self.tr("err_invalid_output"))
            return None

        mode = self.mode_var.get()
        every_n = max(1, int(self.every_n_var.get()))
        target_fps = float(self.target_fps_var.get())
        if mode == "target_fps" and target_fps <= 0:
            messagebox.showerror(self.tr("dlg_error_title"), self.tr("err_targetfps_invalid"))
            return None

        start_sec = max(0.0, float(self.start_var.get()))
        end_sec = float(self.end_var.get())

        fmt = self.format_var.get().lower()
        if fmt not in {"png", "jpg", "webp"}:
            messagebox.showerror(self.tr("dlg_error_title"), self.tr("err_invalid_format"))
            return None

        return ExtractConfig(
            input_path=in_path,
            output_root=out_root,
            create_subfolder=bool(self.create_subfolder_var.get()),
            subfolder_name=sanitize_name(self.subfolder_var.get()),
            mode=mode,
            every_n=every_n,
            target_fps=target_fps,
            start_sec=start_sec,
            end_sec=end_sec,
            resize_mode=self.resize_mode_var.get(),
            max_width=max(1, int(self.max_w_var.get())),
            max_height=max(1, int(self.max_h_var.get())),
            format=fmt,
            quality=max(1, min(100, int(self.quality_var.get()))),
            digits=max(3, min(12, int(self.digits_var.get()))),
            overwrite=bool(self.overwrite_var.get()),
            skip_existing=bool(self.skip_existing_var.get()),
        )

    def start_extract(self):
        if self.worker and self.worker.is_alive():
            return

        cfg = self._make_config()
        if not cfg:
            return

        self.stop_event.clear()
        self.progress["value"] = 0
        self.progress["maximum"] = 100
        self.status_var.set(self.tr("status_starting"))

        self.append_log(self.tr("log_input", path=cfg.input_path))
        self.append_log(self.tr("log_output", path=cfg.output_root))
        self.append_log(self.tr("log_sep"))

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        self.worker = threading.Thread(target=self._run_extract, args=(cfg,), daemon=True)
        self.worker.start()

    def stop_extract(self):
        self.stop_event.set()
        self.append_log(self.tr("status_stop_requested"))

    def _run_extract(self, cfg: ExtractConfig):
        t0 = time.time()

        cap = cv2.VideoCapture(str(cfg.input_path))
        if not cap.isOpened():
            self.q.put(("error", self.tr("err_open_failed")))
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if fps <= 0.0:
            fps = 30.0

        start_frame = int(round(cfg.start_sec * fps))
        if total_frames > 0:
            start_frame = max(0, min(start_frame, total_frames - 1))
        else:
            start_frame = max(0, start_frame)

        if cfg.end_sec and cfg.end_sec > 0:
            end_frame = int(round(cfg.end_sec * fps))
            if total_frames > 0:
                end_frame = max(0, min(end_frame, total_frames))
            end_frame = max(end_frame, start_frame + 1)
        else:
            end_frame = total_frames if total_frames > 0 else None

        out_dir = cfg.output_root
        if cfg.create_subfolder:
            out_dir = out_dir / cfg.subfolder_name
        out_dir.mkdir(parents=True, exist_ok=True)

        cap.set(cv2.CAP_PROP_POS_FRAMES, float(start_frame))

        if cfg.mode == "all":
            keep_rule = ("all", None)
        elif cfg.mode == "every_n":
            keep_rule = ("every_n", max(1, cfg.every_n))
        else:
            keep_rule = ("target_fps", max(0.1, cfg.target_fps))

        frame_index = start_frame
        saved_index = 0

        next_keep = float(start_frame)
        interval = None
        if keep_rule[0] == "target_fps":
            interval = fps / keep_rule[1]
            if interval < 1.0:
                interval = 1.0

        if end_frame is not None and total_frames > 0:
            scan_frames = max(1, end_frame - start_frame)
        elif total_frames > 0:
            scan_frames = max(1, total_frames - start_frame)
        else:
            scan_frames = None

        self.q.put(("progress_setup", scan_frames))

        def resize_frame(bgr):
            if cfg.resize_mode == "none":
                return bgr
            h, w = bgr.shape[:2]
            if cfg.resize_mode == "max_width":
                if w <= cfg.max_width:
                    return bgr
                scale = cfg.max_width / float(w)
                nh = int(round(h * scale))
                return cv2.resize(bgr, (cfg.max_width, nh), interpolation=cv2.INTER_AREA)
            if cfg.resize_mode == "max_height":
                if h <= cfg.max_height:
                    return bgr
                scale = cfg.max_height / float(h)
                nw = int(round(w * scale))
                return cv2.resize(bgr, (nw, cfg.max_height), interpolation=cv2.INTER_AREA)
            scale = min(cfg.max_width / float(w), cfg.max_height / float(h))
            if scale >= 1.0:
                return bgr
            nw = int(round(w * scale))
            nh = int(round(h * scale))
            return cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA)

        def imwrite_params():
            if cfg.format == "jpg":
                return [int(cv2.IMWRITE_JPEG_QUALITY), int(cfg.quality)]
            if cfg.format == "webp":
                return [int(cv2.IMWRITE_WEBP_QUALITY), int(cfg.quality)]
            return []

        params = imwrite_params()

        while True:
            if self.stop_event.is_set():
                break

            if end_frame is not None and frame_index >= end_frame:
                break

            ok, frame = cap.read()
            if not ok:
                break

            keep = False
            if keep_rule[0] == "all":
                keep = True
            elif keep_rule[0] == "every_n":
                n = keep_rule[1]
                keep = ((frame_index - start_frame) % n == 0)
            else:
                if frame_index + 1e-6 >= next_keep:
                    keep = True
                    next_keep += interval

            if keep:
                out_name = f"frame_{saved_index:0{cfg.digits}d}.{cfg.format}"
                out_path = out_dir / out_name

                should_write = True
                if out_path.exists() and cfg.skip_existing and not cfg.overwrite:
                    should_write = False

                if should_write:
                    frame2 = resize_frame(frame)
                    cv2.imwrite(str(out_path), frame2, params)

                saved_index += 1

            if scan_frames is not None:
                scanned = frame_index - start_frame + 1
                elapsed = time.time() - t0
                rate = scanned / elapsed if elapsed > 0 else 0.0
                remaining = (scan_frames - scanned) / rate if rate > 0 else None
                self.q.put(("progress", scanned, scan_frames, saved_index, remaining))
            else:
                elapsed = time.time() - t0
                self.q.put(("progress_unknown", frame_index - start_frame + 1, saved_index, elapsed))

            frame_index += 1

        cap.release()
        dt = time.time() - t0
        self.q.put(("done", saved_index, dt, str(out_dir)))

    def _poll_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]

                if kind == "error":
                    self.append_log(self.tr("dlg_error_title") + ": " + item[1])
                    messagebox.showerror(self.tr("dlg_error_title"), item[1])
                    self._set_idle()

                elif kind == "progress_setup":
                    scan_frames = item[1]
                    if scan_frames is None:
                        self.progress.configure(mode="indeterminate")
                        self.progress.start(8)
                    else:
                        self.progress.stop()
                        self.progress.configure(mode="determinate", maximum=scan_frames)
                        self.progress["value"] = 0

                elif kind == "progress":
                    scanned, total, saved, remaining = item[1], item[2], item[3], item[4]
                    self.progress["value"] = scanned
                    eta = ""
                    if remaining is not None:
                        eta = self.tr("eta_fmt", secs=int(remaining))
                    self.status_var.set(self.tr("status_progress_eta", scanned=scanned, total=total, saved=saved, eta=eta))

                elif kind == "progress_unknown":
                    scanned, saved, elapsed = item[1], item[2], item[3]
                    self.status_var.set(self.tr("status_progress_unknown", scanned=scanned, saved=saved, secs=int(elapsed)))

                elif kind == "done":
                    count, dt, out_dir = item[1], item[2], item[3]
                    self.append_log(self.tr("log_sep"))
                    self.append_log(f"{self.tr('dlg_done_title')}. {dt:.2f}s")
                    self.append_log(f"Output: {out_dir}")
                    self._set_idle()
                    messagebox.showinfo(self.tr("dlg_done_title"), self.tr("done_msg", count=count, out_dir=out_dir))

        except queue.Empty:
            pass

        self.after(80, self._poll_queue)

    def _set_idle(self):
        self.stop_event.set()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.progress.stop()
        if str(self.progress["mode"]) == "indeterminate":
            self.progress["value"] = 0
        self.status_var.set(self.tr("status_ready"))


if __name__ == "__main__":
    app = FrameExtractorGUI()
    app.mainloop()
