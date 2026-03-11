import os
import logging
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

from audio_engine import MusicEngine
from library import Library
from campaign import (CampaignManager, Campaign, Character, DEFAULT_STATS,
                      BattleMap, MapToken, TOKEN_COLORS, TOKEN_ICONS,
                      VALID_TOKEN_TYPES)
from combat_utils import hp_from_stats, initiative_from_dex

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to import tkinterdnd2 for native drag-and-drop
# ---------------------------------------------------------------------------
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
    logger.info("tkinterdnd2 available -- drag & drop enabled")
except ImportError:
    HAS_DND = False
    logger.info("tkinterdnd2 not found -- using file dialog fallback")

# ---------------------------------------------------------------------------
# Try to import PIL for battle map images
# ---------------------------------------------------------------------------
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
    logger.info("Pillow available -- battle map images enabled")
except ImportError:
    HAS_PIL = False
    logger.warning("Pillow not found -- battle maps will have no background image. "
                   "Install with: pip install Pillow")

# ---------------------------------------------------------------------------
# Color palette  (dark theme)
# ---------------------------------------------------------------------------
C = {
    "bg":           "#1e1e2e",
    "bg_panel":     "#282840",
    "bg_card":      "#313150",
    "bg_card_hover":"#3b3b60",
    "bg_entry":     "#3b3b60",
    "fg":           "#cdd6f4",
    "fg_dim":       "#6c7086",
    "accent":       "#cba6f7",
    "accent2":      "#f38ba8",
    "accent3":      "#a6e3a1",
    "amber":        "#f9e2af",
    "blue":         "#89b4fa",
    "btn_bg":       "#45475a",
    "btn_hover":    "#585b70",
    "stop_bg":      "#f38ba8",
    "stop_fg":      "#1e1e2e",
    "cat_bg":       "#45475a",
    "cat_active":   "#cba6f7",
    "cat_active_fg":"#1e1e2e",
    "scrollbar":    "#45475a",
    "border":       "#45475a",
    "stat_high":    "#a6e3a1",
    "stat_mid":     "#f9e2af",
    "stat_low":     "#f38ba8",
    "grid_line":    "#ffffff30",
    "token_outline":"#1e1e2e",
}

FONT       = ("Segoe UI", 10)
FONT_BOLD  = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 13, "bold")
FONT_BIG   = ("Segoe UI", 16, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_TINY  = ("Segoe UI", 8)
FONT_STAT  = ("Consolas", 12, "bold")

AUDIO_EXTS = {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".opus", ".aac", ".wma"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


# ======================================================================
# Styled helpers
# ======================================================================
def make_button(parent, text, command, bg=None, fg=None,
                font=None, padx=10, pady=4, **kw):
    bg = bg or C["btn_bg"]
    fg = fg or C["fg"]
    font = font or FONT
    btn = tk.Label(parent, text=text, bg=bg, fg=fg, font=font,
                   padx=padx, pady=pady, cursor="hand2", **kw)
    btn.bind("<Button-1>", lambda e: command())
    btn.bind("<Enter>", lambda e: btn.configure(bg=C["btn_hover"]))
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
    return btn


def make_stop_button(parent, text, command):
    btn = tk.Label(parent, text=text, bg=C["stop_bg"], fg=C["stop_fg"],
                   font=FONT_BOLD, padx=12, pady=4, cursor="hand2")
    btn.bind("<Button-1>", lambda e: command())
    btn.bind("<Enter>", lambda e: btn.configure(bg="#e06080"))
    btn.bind("<Leave>", lambda e: btn.configure(bg=C["stop_bg"]))
    return btn


def make_volume_slider(parent, label, initial, command):
    frame = tk.Frame(parent, bg=C["bg"])
    tk.Label(frame, text=label, bg=C["bg"], fg=C["fg_dim"],
             font=FONT_TINY).pack(side="left", padx=(0, 2))
    scale = ttk.Scale(frame, from_=0, to=100, orient="horizontal",
                      length=100,
                      command=lambda v: command(float(v)))
    scale.set(initial)
    scale.pack(side="left")
    return frame


# ======================================================================
# Category tab bar  (reused in Soundboard and Characters)
# ======================================================================
class CategoryBar(tk.Frame):
    def __init__(self, parent, on_select, on_add_category, add_label="+ Category"):
        super().__init__(parent, bg=C["bg_panel"])
        self._on_select = on_select
        self._cats = []
        self._selected = None
        self._btns = []

        self._scroll = tk.Frame(self, bg=C["bg_panel"])
        self._scroll.pack(side="left", fill="x", expand=True)

        self._add_btn = make_button(self, add_label, on_add_category,
                                    bg=C["accent"], fg=C["bg"],
                                    font=FONT_SMALL, padx=8, pady=2)
        self._add_btn.pack(side="right", padx=(4, 0))

    def set_categories(self, cats, selected=None):
        self._cats = cats
        if selected and selected in cats:
            self._selected = selected
        elif cats:
            self._selected = cats[0]
        else:
            self._selected = None
        self._rebuild()

    @property
    def selected(self):
        return self._selected

    def _rebuild(self):
        for b in self._btns:
            b.destroy()
        self._btns.clear()
        for cat in self._cats:
            active = (cat == self._selected)
            bg = C["cat_active"] if active else C["cat_bg"]
            fg = C["cat_active_fg"] if active else C["fg"]
            lbl = tk.Label(self._scroll, text=cat, bg=bg, fg=fg,
                           font=FONT_SMALL, padx=10, pady=3, cursor="hand2")
            lbl.pack(side="left", padx=2, pady=2)
            lbl.bind("<Button-1>", lambda e, c=cat: self._click(c))
            lbl.bind("<Button-3>", lambda e, c=cat: self._right_click(e, c))
            self._btns.append(lbl)

    def _click(self, cat):
        self._selected = cat
        self._rebuild()
        self._on_select(cat)

    def _right_click(self, event, cat):
        menu = tk.Menu(self, tearoff=0, bg=C["bg_card"], fg=C["fg"],
                       activebackground=C["btn_hover"], activeforeground=C["fg"])
        menu.add_command(label=f"Delete '{cat}'",
                         command=lambda: self._on_select(("__delete__", cat)))
        menu.tk_popup(event.x_root, event.y_root)


# ======================================================================
# Track list inside a category
# ======================================================================
class TrackList(tk.Frame):
    def __init__(self, parent, kind, library, engine, status_cb):
        super().__init__(parent, bg=C["bg_panel"])
        self._kind = kind
        self._lib = library
        self._engine = engine
        self._status_cb = status_cb
        self._category = None
        self._tracks = []

        hdr = tk.Frame(self, bg=C["bg_panel"])
        hdr.pack(fill="x", padx=4, pady=(4, 0))
        self._add_btn = make_button(hdr, "+ Track", self._add_track,
                                    font=FONT_SMALL, padx=8, pady=2)
        self._add_btn.pack(side="right")

        self._hint = tk.Label(self, text="drag & drop audio files here",
                              bg=C["bg_panel"], fg=C["fg_dim"], font=FONT_TINY)
        self._hint.pack(pady=(2, 0))

        container = tk.Frame(self, bg=C["bg_panel"])
        container.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(container, bg=C["bg_panel"], highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(container, orient="vertical",
                                        command=self._canvas.yview)
        self._inner = tk.Frame(self._canvas, bg=C["bg_panel"])
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))
        self._canvas_win = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.pack(side="right", fill="y")

        self._canvas.bind("<Enter>",
                          lambda e: self._canvas.bind_all("<MouseWheel>", self._on_wheel))
        self._canvas.bind("<Leave>",
                          lambda e: self._canvas.unbind_all("<MouseWheel>"))

        if HAS_DND:
            try:
                self.drop_target_register(DND_FILES)
                self.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

    def _on_canvas_resize(self, event):
        self._canvas.itemconfig(self._canvas_win, width=event.width)

    def _on_wheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def show_category(self, category):
        self._category = category
        self._refresh()

    def _refresh(self):
        for w in self._inner.winfo_children():
            w.destroy()
        if not self._category:
            return
        self._tracks = self._lib.tracks_in_category(self._category, self._kind)
        for t in self._tracks:
            self._make_track_card(t)

    def _make_track_card(self, track):
        if self._kind == "fast_stinger":
            self._make_fast_card(track)
            return

        card = tk.Frame(self._inner, bg=C["bg_card"], cursor="hand2")
        card.pack(fill="x", padx=4, pady=2, ipady=6)

        play_icon = tk.Label(card, text="\u25B6", bg=C["bg_card"],
                             fg=C["accent3"], font=FONT, padx=8)
        play_icon.pack(side="left")

        name_lbl = tk.Label(card, text=track.name, bg=C["bg_card"],
                            fg=C["fg"], font=FONT, anchor="w")
        name_lbl.pack(side="left", fill="x", expand=True, padx=4)

        for w in (card, play_icon, name_lbl):
            w.bind("<Enter>", lambda e: [x.configure(bg=C["bg_card_hover"])
                                         for x in (card, play_icon, name_lbl)])
            w.bind("<Leave>", lambda e: [x.configure(bg=C["bg_card"])
                                         for x in (card, play_icon, name_lbl)])
            w.bind("<Button-1>", lambda e, t=track: self._play(t))
            w.bind("<Button-3>", lambda e, t=track: self._right_click_track(e, t))

    def _make_fast_card(self, track):
        hotkey = track.hotkey or "?"
        card = tk.Frame(self._inner, bg=C["amber"], cursor="hand2")
        card.pack(side="left", padx=4, pady=4, ipadx=8, ipady=6)

        tk.Label(card, text=track.name, bg=C["amber"],
                 fg=C["bg"], font=FONT_SMALL).pack()
        tk.Label(card, text=f"[{hotkey}]", bg=C["amber"],
                 fg=C["bg_card"], font=FONT_TINY).pack()

        card.bind("<Button-1>", lambda e, t=track: self._play(t))
        card.bind("<Button-3>", lambda e, t=track: self._right_click_fast(e, t))

    def _play(self, track):
        try:
            if self._kind == "ambient":
                self._engine.play_ambient(track.name)
                self._status_cb(f"\u266B {track.name}")
            elif self._kind == "stinger":
                self._engine.play_stinger(track.name)
                self._status_cb(f"\u26A1 {track.name}")
            elif self._kind == "fast_stinger":
                self._engine.play_fast_stinger(track.name)
                self._status_cb(f"\u26A1 Fast: {track.name}")
        except Exception as ex:
            logger.error("Play error: %s", ex)

    def _right_click_track(self, event, track):
        menu = tk.Menu(self, tearoff=0, bg=C["bg_card"], fg=C["fg"],
                       activebackground=C["btn_hover"], activeforeground=C["fg"])
        menu.add_command(label=f"Delete '{track.name}'",
                         command=lambda: self._delete_track(track))
        menu.tk_popup(event.x_root, event.y_root)

    def _right_click_fast(self, event, track):
        menu = tk.Menu(self, tearoff=0, bg=C["bg_card"], fg=C["fg"],
                       activebackground=C["btn_hover"], activeforeground=C["fg"])
        menu.add_command(label="Change hotkey",
                         command=lambda: self._change_hotkey(track))
        menu.add_command(label=f"Delete '{track.name}'",
                         command=lambda: self._delete_track(track))
        menu.tk_popup(event.x_root, event.y_root)

    def _change_hotkey(self, track):
        win = tk.Toplevel(self.winfo_toplevel())
        win.title("Press a key")
        win.geometry("260x100")
        win.configure(bg=C["bg"])
        win.transient(self.winfo_toplevel())
        win.grab_set()
        tk.Label(win, text="Press any key to assign...",
                 bg=C["bg"], fg=C["fg"], font=FONT).pack(expand=True)

        def _capture(event):
            track.hotkey = event.keysym
            self._lib.update_hotkey(track.name, track.hotkey)
            win.destroy()
            self._refresh()

        win.bind("<Key>", _capture)
        win.focus_force()

    def _delete_track(self, track):
        self._lib.remove_track(track.name)
        self._engine.unload_track(track.name)
        self._refresh()

    def _add_track(self):
        if not self._category:
            messagebox.showinfo("Info", "Select a category first.")
            return
        paths = filedialog.askopenfilenames(
            title="Select audio files",
            filetypes=[("Audio", " ".join(f"*{e}" for e in AUDIO_EXTS))])
        for p in paths:
            self._import_file(p)

    def _import_file(self, path):
        if not self._category:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in AUDIO_EXTS:
            return
        name = os.path.splitext(os.path.basename(path))[0]
        hotkey = ""
        if self._kind == "fast_stinger":
            win = tk.Toplevel(self.winfo_toplevel())
            win.title("Assign hotkey")
            win.geometry("260x100")
            win.configure(bg=C["bg"])
            win.transient(self.winfo_toplevel())
            win.grab_set()
            tk.Label(win, text="Press a key to assign\nor Escape to skip",
                     bg=C["bg"], fg=C["fg"], font=FONT).pack(expand=True)
            result = {"key": ""}

            def _cap(event):
                if event.keysym != "Escape":
                    result["key"] = event.keysym
                win.destroy()

            win.bind("<Key>", _cap)
            win.focus_force()
            win.wait_window()
            hotkey = result["key"]

        track = self._lib.add_track(path, name, self._category,
                                    self._kind, hotkey=hotkey)
        try:
            self._engine.load_track(track.name, self._lib.track_path(track))
        except Exception as ex:
            logger.warning("Could not load '%s': %s", name, ex)
        self._refresh()

    def _on_drop(self, event):
        data = event.data
        if "{" in data:
            paths = []
            for part in data.split("}"):
                part = part.strip().lstrip("{")
                if part:
                    paths.append(part)
        else:
            paths = data.split()
        for p in paths:
            self._import_file(p)

    def handle_hotkey(self, keysym):
        if self._kind != "fast_stinger":
            return False
        for t in self._lib.all_tracks():
            if t.kind == "fast_stinger" and t.hotkey == keysym:
                self._play(t)
                return True
        return False


# ======================================================================
# Sound Panel  (Ambient / Stingers / Fast Stingers)
# ======================================================================
class SoundPanel(tk.Frame):
    def __init__(self, parent, title, kind, library, engine, status_cb):
        super().__init__(parent, bg=C["bg_panel"], bd=0)
        self._kind = kind
        self._lib = library

        title_frame = tk.Frame(self, bg=C["bg_panel"])
        title_frame.pack(fill="x", padx=8, pady=(8, 2))
        tk.Label(title_frame, text=title, bg=C["bg_panel"],
                 fg=C["accent"], font=FONT_TITLE).pack(side="left")

        self._now_playing_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self._now_playing_var,
                 bg=C["bg_panel"], fg=C["accent3"],
                 font=FONT_SMALL, anchor="w"
                 ).pack(fill="x", padx=12, pady=(0, 2))

        self._cat_bar = CategoryBar(self, self._on_cat_select,
                                    self._on_add_category)
        self._cat_bar.pack(fill="x", padx=8, pady=(0, 4))

        self._track_view = TrackList(self, kind, library, engine, status_cb)
        self._track_view.pack(fill="both", expand=True, padx=4, pady=4)

        self.refresh()

    def refresh(self):
        cats = self._lib.categories(self._kind)
        sel = self._cat_bar.selected
        self._cat_bar.set_categories(cats, sel)
        if self._cat_bar.selected:
            self._track_view.show_category(self._cat_bar.selected)

    def _on_cat_select(self, cat):
        if isinstance(cat, tuple) and cat[0] == "__delete__":
            cat_name = cat[1]
            tracks = self._lib.tracks_in_category(cat_name, self._kind)
            if tracks:
                if not messagebox.askyesno(
                        "Confirm",
                        f"Delete category '{cat_name}' and {len(tracks)} tracks?"):
                    return
                for t in tracks:
                    self._lib.remove_track(t.name)
            self.refresh()
            return
        self._track_view.show_category(cat)

    def _on_add_category(self):
        name = simpledialog.askstring(
            "New Category",
            f"Category name for {self._kind.upper()}:",
            parent=self.winfo_toplevel())
        if not name or not name.strip():
            return
        name = name.strip()
        cats = self._lib.categories(self._kind)
        if name not in cats:
            self._cat_bar.set_categories(cats + [name], name)
            self._track_view.show_category(name)

    def set_now_playing(self, text):
        self._now_playing_var.set(text)

    def clear_now_playing(self):
        self._now_playing_var.set("")

    @property
    def fast_panel(self):
        if self._kind == "fast_stinger":
            return self._track_view
        return None


# ======================================================================
# Character Editor Window  (stat block)
# ======================================================================
class CharacterEditor(tk.Toplevel):
    STAT_KEYS = ["str", "dex", "con", "int", "wis", "cha"]
    EXTRA_KEYS = ["ac", "hp", "speed", "cr"]

    def __init__(self, parent, campaign_mgr, campaign_id, character=None,
                 char_type="enemy", category="", on_save=None):
        super().__init__(parent)
        self._cm = campaign_mgr
        self._cid = campaign_id
        self._char = character
        self._on_save = on_save
        self._is_new = character is None

        if self._is_new:
            self._char = Character(char_type=char_type, category=category)

        self.title(f"{'New' if self._is_new else 'Edit'} Character")
        self.geometry("700x750")
        self.configure(bg=C["bg"])
        self.transient(parent)
        self.grab_set()

        outer = tk.Frame(self, bg=C["bg"])
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=C["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self._content = tk.Frame(canvas, bg=C["bg"])
        self._content.bind("<Configure>",
                           lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        canvas.bind("<Configure>",
                     lambda e: canvas.itemconfig(
                         canvas.find_withtag("all")[0], width=e.width - 20)
                     if canvas.find_withtag("all") else None)

        self._entries = {}
        self._build_form()

    def _make_section(self, title):
        tk.Label(self._content, text=title, bg=C["bg"], fg=C["accent"],
                 font=FONT_BOLD, anchor="w").pack(fill="x", padx=16, pady=(12, 4))
        tk.Frame(self._content, bg=C["border"], height=1).pack(fill="x", padx=16, pady=(0, 4))

    def _make_field(self, label, key, default="", multiline=False, width=60):
        frame = tk.Frame(self._content, bg=C["bg"])
        frame.pack(fill="x", padx=16, pady=2)
        tk.Label(frame, text=label, bg=C["bg"], fg=C["fg_dim"],
                 font=FONT_SMALL, width=14, anchor="w").pack(side="left")
        val = getattr(self._char, key, default) if not isinstance(default, dict) else default
        if multiline:
            txt = tk.Text(frame, bg=C["bg_entry"], fg=C["fg"],
                          insertbackground=C["fg"], font=FONT,
                          height=4, width=width, bd=1, relief="solid", wrap="word")
            txt.insert("1.0", val)
            txt.pack(side="left", fill="x", expand=True, padx=(4, 0))
            self._entries[key] = txt
        else:
            entry = tk.Entry(frame, bg=C["bg_entry"], fg=C["fg"],
                             insertbackground=C["fg"], font=FONT,
                             width=width, bd=1, relief="solid")
            entry.insert(0, val)
            entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
            self._entries[key] = entry

    def _build_form(self):
        self._make_section("BASIC INFO")
        self._make_field("Name", "name", self._char.name)

        frame = tk.Frame(self._content, bg=C["bg"])
        frame.pack(fill="x", padx=16, pady=2)
        tk.Label(frame, text="Type", bg=C["bg"], fg=C["fg_dim"],
                 font=FONT_SMALL, width=14, anchor="w").pack(side="left")
        self._type_var = tk.StringVar(value=self._char.char_type)
        for val, label in [("enemy", "Enemy"), ("npc", "Key NPC")]:
            rb = tk.Radiobutton(frame, text=label, variable=self._type_var,
                                value=val, bg=C["bg"], fg=C["fg"],
                                selectcolor=C["bg_card"], activebackground=C["bg"],
                                activeforeground=C["fg"], font=FONT_SMALL)
            rb.pack(side="left", padx=(4, 12))

        self._make_field("Category", "category", self._char.category)

        self._make_section("APPEARANCE & LORE")
        self._make_field("Appearance", "appearance", self._char.appearance, multiline=True)
        self._make_field("Backstory", "backstory", self._char.backstory, multiline=True)
        self._make_field("Weaknesses", "weaknesses", self._char.weaknesses, multiline=True)

        self._make_section("ABILITY SCORES")
        stats_frame = tk.Frame(self._content, bg=C["bg"])
        stats_frame.pack(fill="x", padx=16, pady=4)

        for i, key in enumerate(self.STAT_KEYS):
            col_frame = tk.Frame(stats_frame, bg=C["bg_card"], padx=8, pady=6)
            col_frame.pack(side="left", padx=4, pady=2)
            tk.Label(col_frame, text=key.upper(), bg=C["bg_card"],
                     fg=C["accent"], font=FONT_BOLD).pack()
            val = self._char.stats.get(key, 10)
            entry = tk.Entry(col_frame, bg=C["bg_entry"], fg=C["fg"],
                             insertbackground=C["fg"], font=FONT_STAT,
                             width=4, bd=1, relief="solid", justify="center")
            entry.insert(0, str(val))
            entry.pack(pady=(4, 2))
            mod = (int(val) - 10) // 2
            mod_text = f"+{mod}" if mod >= 0 else str(mod)
            mod_color = C["stat_high"] if mod > 0 else (C["stat_low"] if mod < 0 else C["fg_dim"])
            tk.Label(col_frame, text=mod_text, bg=C["bg_card"],
                     fg=mod_color, font=FONT_SMALL).pack()
            self._entries[f"stat_{key}"] = entry

        self._make_section("COMBAT STATS")
        extra_frame = tk.Frame(self._content, bg=C["bg"])
        extra_frame.pack(fill="x", padx=16, pady=4)
        extra_labels = {"ac": "AC", "hp": "HP", "speed": "Speed", "cr": "CR"}
        for key in self.EXTRA_KEYS:
            ef = tk.Frame(extra_frame, bg=C["bg"])
            ef.pack(side="left", padx=(0, 16))
            tk.Label(ef, text=extra_labels[key], bg=C["bg"], fg=C["fg_dim"],
                     font=FONT_SMALL).pack(side="left")
            val = str(self._char.stats.get(key, DEFAULT_STATS.get(key, "")))
            entry = tk.Entry(ef, bg=C["bg_entry"], fg=C["fg"],
                             insertbackground=C["fg"], font=FONT,
                             width=8, bd=1, relief="solid")
            entry.insert(0, val)
            entry.pack(side="left", padx=(4, 0))
            self._entries[f"stat_{key}"] = entry

        self._make_section("ABILITIES & ACTIONS")
        self._make_field("Abilities", "abilities", self._char.abilities, multiline=True)

        self._make_section("DM NOTES")
        self._make_field("Notes", "notes", self._char.notes, multiline=True)

        tk.Frame(self._content, bg=C["border"], height=1).pack(fill="x", padx=16, pady=(16, 8))
        btn_frame = tk.Frame(self._content, bg=C["bg"])
        btn_frame.pack(fill="x", padx=16, pady=(0, 16))

        tk.Button(btn_frame, text="Save Character", font=FONT_BOLD,
                  bg=C["accent"], fg=C["bg"], bd=0,
                  activebackground=C["cat_active"], activeforeground=C["bg"],
                  cursor="hand2", padx=20, pady=8, command=self._save).pack(side="right")
        tk.Button(btn_frame, text="Cancel", font=FONT,
                  bg=C["btn_bg"], fg=C["fg"], bd=0,
                  activebackground=C["btn_hover"], activeforeground=C["fg"],
                  cursor="hand2", padx=16, pady=8,
                  command=self.destroy).pack(side="right", padx=(0, 8))

        if not self._is_new:
            tk.Button(btn_frame, text="Delete", font=FONT,
                      bg=C["stop_bg"], fg=C["stop_fg"], bd=0,
                      activebackground="#e06080", activeforeground=C["stop_fg"],
                      cursor="hand2", padx=16, pady=8,
                      command=self._delete).pack(side="left")

    def _collect_data(self):
        for key, widget in self._entries.items():
            if key.startswith("stat_"):
                continue
            if isinstance(widget, tk.Text):
                val = widget.get("1.0", "end-1c").strip()
            else:
                val = widget.get().strip()
            setattr(self._char, key, val)
        self._char.char_type = self._type_var.get()
        stats = {}
        for key in self.STAT_KEYS + self.EXTRA_KEYS:
            entry = self._entries.get(f"stat_{key}")
            if entry:
                raw = entry.get().strip()
                if key in self.STAT_KEYS:
                    try:
                        stats[key] = int(raw)
                    except ValueError:
                        stats[key] = 10
                else:
                    stats[key] = raw
        self._char.stats = stats

    def _save(self):
        self._collect_data()
        if not self._char.name:
            messagebox.showwarning("Warning", "Character must have a name!", parent=self)
            return
        if not self._char.category:
            messagebox.showwarning("Warning", "Character must have a category!", parent=self)
            return
        self._cm.add_character(self._cid, self._char)
        if self._on_save:
            self._on_save()
        self.destroy()

    def _delete(self):
        if messagebox.askyesno("Confirm",
                               f"Delete character '{self._char.name}'?", parent=self):
            self._cm.remove_character(self._cid, self._char.id)
            if self._on_save:
                self._on_save()
            self.destroy()


# ======================================================================
# Character Panel  (Enemies / Key NPCs)
# ======================================================================
class CharacterPanel(tk.Frame):
    def __init__(self, parent, char_type, char_type_label,
                 campaign_mgr, campaign_id):
        super().__init__(parent, bg=C["bg_panel"], bd=0)
        self._char_type = char_type
        self._cm = campaign_mgr
        self._cid = campaign_id

        title_frame = tk.Frame(self, bg=C["bg_panel"])
        title_frame.pack(fill="x", padx=8, pady=(8, 2))
        tk.Label(title_frame, text=char_type_label, bg=C["bg_panel"],
                 fg=C["accent"], font=FONT_TITLE).pack(side="left")
        make_button(title_frame, "+ Character", self._add_character,
                    bg=C["accent3"], fg=C["bg"],
                    font=FONT_SMALL, padx=8, pady=2).pack(side="right")

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=8, pady=4)

        self._cat_bar = CategoryBar(self, self._on_cat_select,
                                    self._on_add_category, add_label="+ Group")
        self._cat_bar.pack(fill="x", padx=8, pady=(0, 4))

        container = tk.Frame(self, bg=C["bg_panel"])
        container.pack(fill="both", expand=True, padx=4, pady=4)

        self._canvas = tk.Canvas(container, bg=C["bg_panel"], highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(container, orient="vertical",
                                        command=self._canvas.yview)
        self._inner = tk.Frame(self._canvas, bg=C["bg_panel"])
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))
        self._canvas_win = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.pack(side="right", fill="y")

        self._canvas.bind("<Enter>",
                          lambda e: self._canvas.bind_all("<MouseWheel>", self._on_wheel))
        self._canvas.bind("<Leave>",
                          lambda e: self._canvas.unbind_all("<MouseWheel>"))
        self.refresh()

    def _on_canvas_resize(self, event):
        self._canvas.itemconfig(self._canvas_win, width=event.width)

    def _on_wheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def refresh(self):
        cats = self._cm.character_categories(self._cid, self._char_type)
        sel = self._cat_bar.selected
        self._cat_bar.set_categories(cats, sel)
        self._show_category(self._cat_bar.selected)

    def _show_category(self, category):
        for w in self._inner.winfo_children():
            w.destroy()
        if not category:
            return
        chars = self._cm.characters_in_category(self._cid, category, self._char_type)
        for ch in chars:
            self._make_char_card(ch)

    def _make_char_card(self, char):
        card = tk.Frame(self._inner, bg=C["bg_card"], cursor="hand2")
        card.pack(fill="x", padx=4, pady=3, ipady=8)

        icon_text = "\u2694" if char.char_type == "enemy" else "\u2655"
        icon_color = C["accent2"] if char.char_type == "enemy" else C["blue"]
        icon = tk.Label(card, text=icon_text, bg=C["bg_card"], fg=icon_color,
                        font=("Segoe UI", 16), padx=8)
        icon.pack(side="left")

        info = tk.Frame(card, bg=C["bg_card"])
        info.pack(side="left", fill="x", expand=True, padx=4)
        name_lbl = tk.Label(info, text=char.name, bg=C["bg_card"],
                            fg=C["fg"], font=FONT_BOLD, anchor="w")
        name_lbl.pack(fill="x")

        stats = char.stats
        stat_parts = []
        if stats.get("hp"):
            stat_parts.append(f"HP {stats['hp']}")
        if stats.get("ac"):
            stat_parts.append(f"AC {stats['ac']}")
        if stats.get("cr"):
            stat_parts.append(f"CR {stats['cr']}")
        stat_line = "  |  ".join(stat_parts) if stat_parts else ""
        if stat_line:
            tk.Label(info, text=stat_line, bg=C["bg_card"],
                     fg=C["fg_dim"], font=FONT_TINY, anchor="w").pack(fill="x")

        scores_frame = tk.Frame(card, bg=C["bg_card"])
        scores_frame.pack(side="right", padx=8)
        for key in ["str", "dex", "con", "int", "wis", "cha"]:
            val = stats.get(key, 10)
            try:
                val_int = int(val)
            except (ValueError, TypeError):
                val_int = 10
            color = C["stat_high"] if val_int >= 14 else (C["stat_low"] if val_int <= 7 else C["fg_dim"])
            tk.Label(scores_frame, text=f"{key[:2].upper()}{val}",
                     bg=C["bg_card"], fg=color, font=FONT_TINY, padx=3).pack(side="left")

        all_widgets = [card, icon, info, name_lbl, scores_frame]
        for w in all_widgets:
            w.bind("<Enter>", lambda e: [x.configure(bg=C["bg_card_hover"])
                                         for x in all_widgets
                                         if isinstance(x, (tk.Frame, tk.Label))])
            w.bind("<Leave>", lambda e: [x.configure(bg=C["bg_card"])
                                         for x in all_widgets
                                         if isinstance(x, (tk.Frame, tk.Label))])
            w.bind("<Button-1>", lambda e, c=char: self._edit_character(c))

    def _edit_character(self, char):
        CharacterEditor(self.winfo_toplevel(), self._cm, self._cid,
                        character=char, on_save=self.refresh)

    def _add_character(self):
        category = self._cat_bar.selected or ""
        CharacterEditor(self.winfo_toplevel(), self._cm, self._cid,
                        char_type=self._char_type, category=category,
                        on_save=self.refresh)

    def _on_cat_select(self, cat):
        if isinstance(cat, tuple) and cat[0] == "__delete__":
            cat_name = cat[1]
            chars = self._cm.characters_in_category(self._cid, cat_name, self._char_type)
            if chars:
                if not messagebox.askyesno(
                        "Confirm",
                        f"Delete group '{cat_name}' and all {len(chars)} characters in it?"):
                    return
                for ch in chars:
                    self._cm.remove_character(self._cid, ch.id)
            self.refresh()
            return
        self._show_category(cat)

    def _on_add_category(self):
        name = simpledialog.askstring(
            "New Group",
            f"Group name for {self._char_type.upper()}S:",
            parent=self.winfo_toplevel())
        if not name or not name.strip():
            return
        name = name.strip()
        cats = self._cm.character_categories(self._cid, self._char_type)
        if name not in cats:
            self._cat_bar.set_categories(cats + [name], name)
            self._show_category(name)
        else:
            self._cat_bar.set_categories(cats, name)
            self._show_category(name)


# ======================================================================
# Characters Tab
# ======================================================================
class CharactersTab(tk.Frame):
    def __init__(self, parent, campaign_mgr, campaign_id):
        super().__init__(parent, bg=C["bg"])
        panels = tk.Frame(self, bg=C["bg"])
        panels.pack(fill="both", expand=True, padx=10, pady=8)
        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=1)
        panels.rowconfigure(0, weight=1)

        self._enemies = CharacterPanel(panels, "enemy", "ENEMIES",
                                       campaign_mgr, campaign_id)
        self._enemies.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self._npcs = CharacterPanel(panels, "npc", "KEY NPCs",
                                    campaign_mgr, campaign_id)
        self._npcs.grid(row=0, column=1, sticky="nsew", padx=(4, 0))


# ======================================================================
# Soundboard Tab
# ======================================================================
class SoundboardTab(tk.Frame):
    def __init__(self, parent, library, engine):
        super().__init__(parent, bg=C["bg"])
        self._lib = library
        self._engine = engine

        top = tk.Frame(self, bg=C["bg"], height=48)
        top.pack(fill="x", padx=10, pady=(8, 4))

        self._status_var = tk.StringVar(value="Nothing playing")
        tk.Label(top, textvariable=self._status_var, bg=C["bg"],
                 fg=C["fg"], font=FONT_BOLD, anchor="w"
                 ).pack(side="left", fill="x", expand=True)

        make_volume_slider(top, "Amb:", 80, self._on_vol_amb).pack(side="left", padx=4)
        engine.set_ambient_volume(0.8)
        make_volume_slider(top, "Stng:", 80, self._on_vol_stng).pack(side="left", padx=4)
        engine.set_stinger_volume(0.8)
        make_volume_slider(top, "Fast:", 80, self._on_vol_fast).pack(side="left", padx=4)
        engine.set_fast_stinger_volume(0.8)

        make_stop_button(top, "STOP ALL", self._on_stop_all).pack(side="right", padx=(4, 0))
        make_stop_button(top, "STOP Stng", self._on_stop_stinger).pack(side="right", padx=4)
        make_stop_button(top, "STOP Amb", self._on_stop_ambient).pack(side="right", padx=4)

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=10)

        panels = tk.Frame(self, bg=C["bg"])
        panels.pack(fill="both", expand=True, padx=10, pady=8)
        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=1)
        panels.columnconfigure(2, weight=1)
        panels.rowconfigure(0, weight=1)

        self._p_ambient = SoundPanel(panels, "AMBIENT", "ambient",
                                     library, engine, self._set_status)
        self._p_ambient.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self._p_stinger = SoundPanel(panels, "STINGERS", "stinger",
                                     library, engine, self._set_status)
        self._p_stinger.grid(row=0, column=1, sticky="nsew", padx=4)

        self._p_fast = SoundPanel(panels, "FAST STINGERS", "fast_stinger",
                                  library, engine, self._set_status)
        self._p_fast.grid(row=0, column=2, sticky="nsew", padx=(4, 0))

    def _set_status(self, text):
        self._status_var.set(text)
        if text.startswith("\u266B"):
            self._p_ambient.set_now_playing(text)
        elif "Fast:" in text:
            self._p_fast.set_now_playing(text)
        elif text.startswith("\u26A1"):
            self._p_stinger.set_now_playing(text)

    def _on_vol_amb(self, val):
        self._engine.set_ambient_volume(val / 100.0)

    def _on_vol_stng(self, val):
        self._engine.set_stinger_volume(val / 100.0)

    def _on_vol_fast(self, val):
        self._engine.set_fast_stinger_volume(val / 100.0)

    def _on_stop_all(self):
        self._engine.stop_all()
        self._status_var.set("Stopped")
        self._p_ambient.clear_now_playing()
        self._p_stinger.clear_now_playing()
        self._p_fast.clear_now_playing()

    def _on_stop_ambient(self):
        self._engine.stop_ambient()
        self._status_var.set("Ambient stopped")
        self._p_ambient.clear_now_playing()

    def _on_stop_stinger(self):
        self._engine.stop_stinger()
        self._status_var.set("Stinger stopped")
        self._p_stinger.clear_now_playing()

    def handle_hotkey(self, keysym):
        fp = self._p_fast.fast_panel
        if fp:
            return fp.handle_hotkey(keysym)
        return False


# ======================================================================
# Battle Map Tab
# ======================================================================
class BattleMapTab(tk.Frame):
    """Interactive battle map with exploration/combat modes."""

    def __init__(self, parent, campaign_mgr, campaign_id):
        super().__init__(parent, bg=C["bg"])
        self._cm = campaign_mgr
        self._cid = campaign_id
        self._current_map = None
        self._bg_image = None
        self._bg_photo = None
        self._dragging = None
        self._zoom = 1.0

        self._combat_mode = False
        self._turn_order = []
        self._turn_index = 0
        self._characters = []

        toolbar = tk.Frame(self, bg=C["bg"])
        toolbar.pack(fill="x", padx=10, pady=(8, 4))

        tk.Label(toolbar, text="BATTLE MAP", bg=C["bg"], fg=C["accent"],
                 font=FONT_TITLE).pack(side="left")

        self._map_var = tk.StringVar(value="-- select map --")
        self._map_combo = ttk.Combobox(toolbar, textvariable=self._map_var,
                                       state="readonly", width=25)
        self._map_combo.pack(side="left", padx=(16, 4))
        self._map_combo.bind("<<ComboboxSelected>>", self._on_map_selected)

        make_button(toolbar, "+ New Map", self._new_map,
                    bg=C["accent"], fg=C["bg"],
                    font=FONT_SMALL, padx=8, pady=2).pack(side="left", padx=4)
        make_button(toolbar, "Delete Map", self._delete_map,
                    bg=C["stop_bg"], fg=C["stop_fg"],
                    font=FONT_SMALL, padx=8, pady=2).pack(side="left", padx=4)

        tk.Label(toolbar, text="Grid:", bg=C["bg"], fg=C["fg_dim"],
                 font=FONT_SMALL).pack(side="left", padx=(16, 4))
        self._rows_var = tk.StringVar(value="20")
        self._cols_var = tk.StringVar(value="20")

        tk.Label(toolbar, text="R:", bg=C["bg"], fg=C["fg_dim"], font=FONT_TINY).pack(side="left")
        rows_entry = tk.Entry(toolbar, textvariable=self._rows_var, bg=C["bg_entry"], fg=C["fg"],
                              insertbackground=C["fg"], font=FONT_SMALL, width=4, bd=1, relief="solid")
        rows_entry.pack(side="left", padx=(2, 4))
        rows_entry.bind("<Return>", lambda e: self._apply_grid())

        tk.Label(toolbar, text="C:", bg=C["bg"], fg=C["fg_dim"], font=FONT_TINY).pack(side="left")
        cols_entry = tk.Entry(toolbar, textvariable=self._cols_var, bg=C["bg_entry"], fg=C["fg"],
                              insertbackground=C["fg"], font=FONT_SMALL, width=4, bd=1, relief="solid")
        cols_entry.pack(side="left", padx=(2, 4))
        cols_entry.bind("<Return>", lambda e: self._apply_grid())

        make_button(toolbar, "Apply Grid", self._apply_grid,
                    font=FONT_SMALL, padx=6, pady=2).pack(side="left", padx=4)

        self._mode_btn = make_button(toolbar, "Enter Combat", self._toggle_mode,
                                     bg=C["accent2"], fg=C["bg"],
                                     font=FONT_SMALL, padx=8, pady=2)
        self._mode_btn.pack(side="left", padx=8)

        make_button(toolbar, "Save", self._save_map,
                    bg=C["accent"], fg=C["bg"],
                    font=FONT_SMALL, padx=8, pady=2).pack(side="right")

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=10)

        body = tk.Frame(self, bg=C["bg_panel"])
        body.pack(fill="both", expand=True, padx=10, pady=8)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0)
        body.rowconfigure(0, weight=1)

        canvas_frame = tk.Frame(body, bg=C["bg_panel"])
        canvas_frame.grid(row=0, column=0, sticky="nsew")

        self._canvas = tk.Canvas(canvas_frame, bg="#2a2a3a", highlightthickness=0, cursor="crosshair")
        self._h_scroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self._canvas.xview)
        self._v_scroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(xscrollcommand=self._h_scroll.set, yscrollcommand=self._v_scroll.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._v_scroll.grid(row=0, column=1, sticky="ns")
        self._h_scroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Button-3>", self._on_right_click)
        self._canvas.bind("<Button-2>", self._on_right_click)
        self._canvas.bind("<Shift-Button-1>", self._on_right_click)
        self._canvas.bind("<Double-Button-1>", self._on_double_click_damage)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)

        side = tk.Frame(body, bg=C["bg_card"], width=230)
        side.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        side.grid_propagate(False)

        tk.Label(side, text="Characters", bg=C["bg_card"], fg=C["accent"], font=FONT_BOLD).pack(anchor="w", padx=8, pady=(8, 2))
        self._char_list = tk.Listbox(side, bg=C["bg_panel"], fg=C["fg"], selectbackground=C["btn_hover"],
                                     height=10, relief="flat")
        self._char_list.pack(fill="x", padx=8)
        make_button(side, "Place Selected", self._add_selected_character_token,
                    font=FONT_SMALL, padx=6, pady=2).pack(anchor="w", padx=8, pady=4)

        tk.Frame(side, bg=C["border"], height=1).pack(fill="x", padx=8, pady=4)
        tk.Label(side, text="Combat", bg=C["bg_card"], fg=C["accent"], font=FONT_BOLD).pack(anchor="w", padx=8)
        self._turn_var = tk.StringVar(value="Turn: -")
        tk.Label(side, textvariable=self._turn_var, bg=C["bg_card"], fg=C["fg"],
                 font=FONT_SMALL, justify="left", wraplength=200).pack(anchor="w", padx=8, pady=(2, 2))
        self._turn_list = tk.Listbox(side, bg=C["bg_panel"], fg=C["fg"], selectbackground=C["btn_hover"],
                                     height=8, relief="flat")
        self._turn_list.pack(fill="x", padx=8, pady=(0, 4))
        make_button(side, "Next Turn", self._next_turn,
                    font=FONT_SMALL, padx=6, pady=2).pack(anchor="w", padx=8, pady=2)
        make_button(side, "Roll Initiative", self._roll_initiative,
                    font=FONT_SMALL, padx=6, pady=2).pack(anchor="w", padx=8, pady=2)

        self._info_var = tk.StringVar(value="No map loaded. Create or select a map.")
        tk.Label(self, textvariable=self._info_var, bg=C["bg"], fg=C["fg_dim"],
                 font=FONT_SMALL).pack(padx=10, pady=(0, 4))

        self._refresh_characters_list()
        self._refresh_map_list()

    def _refresh_characters_list(self):
        self._characters = self._cm.load_characters (self._cid)
        self._char_list.delete(0, tk.END)
        for c in self._characters:
            self._char_list.insert(tk.END, f"[{c.char_type}] {c.name}")

    def _toggle_mode(self):
        self._combat_mode = not self._combat_mode
        if self._combat_mode:
            self._mode_btn.configure(text="Exit Combat", bg=C["accent3"])
            self._roll_initiative()
        else:
            self._mode_btn.configure(text="Enter Combat", bg=C["accent2"])
            self._turn_order = []
            self._turn_index = 0
            self._turn_var.set("Turn: -")
            self._refresh_turn_order_view()
        self._redraw()

    def _refresh_map_list(self):
        maps = self._cm.load_maps(self._cid)
        names = [m.name for m in maps]
        self._map_combo["values"] = names
        if self._current_map and self._current_map.name not in names:
            self._current_map = None
            self._map_var.set("-- select map --")

    def _on_map_selected(self, event=None):
        name = self._map_var.get()
        for m in self._cm.load_maps(self._cid):
            if m.name == name:
                self._current_map = m
                self._rows_var.set(str(m.grid_rows))
                self._cols_var.set(str(m.grid_cols))
                self._load_map_image()
                self._refresh_characters_list()
                self._redraw()
                return

    def _new_map(self):
        name = simpledialog.askstring("New Map", "Map name:", parent=self.winfo_toplevel())
        if not name or not name.strip():
            return
        path = filedialog.askopenfilename(title="Select map image",
                                          filetypes=[("Images", " ".join(f"*{e}" for e in IMAGE_EXTS))])
        if not path:
            return
        rows = int(self._rows_var.get() or 20)
        cols = int(self._cols_var.get() or 20)
        bmap = self._cm.add_map(self._cid, name.strip(), path, rows, cols)
        self._current_map = bmap
        self._refresh_map_list()
        self._map_var.set(bmap.name)
        self._load_map_image()
        self._redraw()

    def _delete_map(self):
        if not self._current_map:
            return
        if messagebox.askyesno("Confirm", f"Delete map '{self._current_map.name}'?", parent=self.winfo_toplevel()):
            self._cm.remove_map(self._cid, self._current_map.id)
            self._current_map = None
            self._bg_image = None
            self._bg_photo = None
            self._canvas.delete("all")
            self._refresh_map_list()
            self._map_var.set("-- select map --")
            self._info_var.set("Map deleted.")

    def _save_map(self):
        if self._current_map:
            self._cm.update_map(self._cid, self._current_map)
            self._info_var.set(f"Map '{self._current_map.name}' saved.")

    def _load_map_image(self):
        if not self._current_map or not HAS_PIL:
            self._bg_image = None
            self._bg_photo = None
            return
        path = self._current_map.image_path
        if not path or not os.path.isfile(path):
            self._bg_image = None
            self._bg_photo = None
            return
        try:
            self._bg_image = Image.open(path)
            self._info_var.set(
                f"Map: {self._current_map.name}  |  "
                f"Image: {self._bg_image.width}x{self._bg_image.height}  |  "
                f"Grid: {self._current_map.grid_rows}x{self._current_map.grid_cols}")
        except Exception as ex:
            logger.error("Failed to load map image: %s", ex)
            self._bg_image = None

    def _apply_grid(self):
        if not self._current_map:
            return
        try:
            rows = max(1, int(self._rows_var.get()))
            cols = max(1, int(self._cols_var.get()))
        except ValueError:
            return
        self._current_map.grid_rows = rows
        self._current_map.grid_cols = cols
        self._cm.update_map(self._cid, self._current_map)
        self._redraw()

    def _add_selected_character_token(self):
        if not self._current_map:
            return
        sel = self._char_list.curselection()
        if not sel:
            return
        char = self._characters[sel[0]]
        hp = hp_from_stats(char.stats, 10)
        token = MapToken(name=char.name, token_type=char.char_type,
                         grid_x=0, grid_y=0, label=char.name[:2].upper(),
                         character_id=char.id, max_hp=hp, current_hp=hp)
        self._current_map.add_token(token)
        self._cm.update_map(self._cid, self._current_map)
        self._redraw()

    def _roll_initiative(self):
        if not self._current_map:
            return
        char_by_id = {c.id: c for c in self._characters}
        for token in self._current_map.tokens:
            dex = 10
            if token.character_id in char_by_id:
                dex = int(char_by_id[token.character_id].stats.get("dex", 10) or 10)
            token.initiative = initiative_from_dex(dex)
        self._turn_order = [t.id for t in sorted(self._current_map.tokens,
                                                 key=lambda t: t.initiative,
                                                 reverse=True)]
        self._turn_index = 0
        self._update_turn_label()
        self._cm.update_map(self._cid, self._current_map)
        self._redraw()

    def _next_turn(self):
        if not self._turn_order:
            self._roll_initiative()
            return
        self._turn_index = (self._turn_index + 1) % len(self._turn_order)
        self._update_turn_label()
        self._redraw()

    def _update_turn_label(self):
        if not self._turn_order or not self._current_map:
            self._turn_var.set("Turn: -")
            self._refresh_turn_order_view()
            return
        tid = self._turn_order[self._turn_index]
        token = next((t for t in self._current_map.tokens if t.id == tid), None)
        if token:
            self._turn_var.set(f"Turn: {token.name} (Init {token.initiative})")
        self._refresh_turn_order_view()

    def _refresh_turn_order_view(self):
        self._turn_list.delete(0, tk.END)
        if not self._current_map or not self._turn_order:
            return
        by_id = {t.id: t for t in self._current_map.tokens}
        for idx, tid in enumerate(self._turn_order):
            token = by_id.get(tid)
            if not token:
                continue
            marker = "→ " if idx == self._turn_index else "  "
            self._turn_list.insert(tk.END, f"{marker}{idx + 1}. {token.name} ({token.initiative})")

    def _redraw(self):
        self._canvas.delete("all")
        if not self._current_map:
            return
        bmap = self._current_map
        rows, cols = bmap.grid_rows, bmap.grid_cols
        if self._bg_image and HAS_PIL:
            img_w, img_h = self._bg_image.width, self._bg_image.height
            scaled_w = int(img_w * self._zoom)
            scaled_h = int(img_h * self._zoom)
            resized = self._bg_image.resize((scaled_w, scaled_h), Image.LANCZOS)
            self._bg_photo = ImageTk.PhotoImage(resized)
            self._canvas.create_image(0, 0, anchor="nw", image=self._bg_photo, tags="bg")
            canvas_w, canvas_h = scaled_w, scaled_h
        else:
            canvas_w = cols * 40
            canvas_h = rows * 40
            self._canvas.create_rectangle(0, 0, canvas_w, canvas_h, fill="#2a2a3a", outline="", tags="bg")

        self._canvas.configure(scrollregion=(0, 0, canvas_w, canvas_h))

        # Pixel-aligned grid coordinates prevent visual jitter on non-even divisions
        x_lines = [round(c * canvas_w / cols) for c in range(cols + 1)]
        y_lines = [round(r * canvas_h / rows) for r in range(rows + 1)]

        # Draw grid lines
        for y in y_lines:
            self._canvas.create_line(0, y, canvas_w, y,
                                     fill="#ffffff", width=1,
                                     tags="grid")
        for x in x_lines:
            self._canvas.create_line(x, 0, x, canvas_h,
                                     fill="#ffffff", width=1,
                                     tags="grid")

        # Draw tokens
        for token in bmap.tokens:
            self._draw_token(token, canvas_w, canvas_h, rows, cols)

    def _draw_token(self, token, canvas_w, canvas_h, rows, cols):
        left = round(token.grid_x * canvas_w / cols)
        right = round((token.grid_x + 1) * canvas_w / cols)
        top = round(token.grid_y * canvas_h / rows)
        bottom = round((token.grid_y + 1) * canvas_h / rows)

        cx = (left + right) / 2
        cy = (top + bottom) / 2
        radius = min(right - left, bottom - top) * 0.4

        # Circle
        self._canvas.create_oval(
            cx - radius, cy - radius, cx + radius, cy + radius,
            fill=token.color, outline=C["token_outline"], width=2,
            tags=(f"token_{token.id}", "token"))

        # Label text
        self._canvas.create_text(
            cx, cy, text=token.label, fill=C["bg"],
            font=("Segoe UI", max(8, int(radius * 0.7)), "bold"),
            tags=(f"token_{token.id}", "token"))

        # Name tooltip above
        self._canvas.create_text(
            cx, cy - radius - 6, text=token.name,
            fill=C["fg"], font=FONT_TINY,
            tags=(f"token_{token.id}", "token"))

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------
    def _add_token(self, token_type):
        if not self._current_map:
            messagebox.showinfo("Info", "Load a map first.", parent=self.winfo_toplevel())
            return
        name = simpledialog.askstring(
            "New Token",
            f"Name for {token_type}:",
            parent=self.winfo_toplevel())
        if not name or not name.strip():
            return
        name = name.strip()
        label = simpledialog.askstring(
            "Token Label",
            f"Short label (1-3 chars, e.g. initials):",
            initialvalue=name[:2].upper(),
            parent=self.winfo_toplevel())
        if not label:
            label = name[:2].upper()

        token = MapToken(name=name, token_type=token_type,
                         grid_x=0, grid_y=0, label=label[:3].upper())
        self._current_map.add_token(token)
        self._cm.update_map(self._cid, self._current_map)
        self._redraw()

    def _find_token_at_canvas(self, cx, cy):
        if not self._current_map:
            return None
        bmap = self._current_map
        rows, cols = bmap.grid_rows, bmap.grid_cols
        if self._bg_image and HAS_PIL:
            canvas_w = int(self._bg_image.width * self._zoom)
            canvas_h = int(self._bg_image.height * self._zoom)
        else:
            canvas_w = cols * 40
            canvas_h = rows * 40

        gx = int(cx * cols / canvas_w)
        gy = int(cy * rows / canvas_h)
        gx = max(0, min(gx, cols - 1))
        gy = max(0, min(gy, rows - 1))
        return bmap.get_token_at(gx, gy), gx, gy

    def _on_press(self, event):
        result = self._find_token_at_canvas(self._canvas.canvasx(event.x), self._canvas.canvasy(event.y))
        if result and result[0]:
            self._dragging = result[0].id

    def _on_drag(self, event):
        if not self._dragging or not self._current_map:
            return
        bmap = self._current_map
        cx = self._canvas.canvasx(event.x)
        cy = self._canvas.canvasy(event.y)
        rows, cols = bmap.grid_rows, bmap.grid_cols
        if self._bg_image and HAS_PIL:
            canvas_w = int(self._bg_image.width * self._zoom)
            canvas_h = int(self._bg_image.height * self._zoom)
        else:
            canvas_w = cols * 40
            canvas_h = rows * 40

        gx = int(cx * cols / canvas_w)
        gy = int(cy * rows / canvas_h)
        gx = max(0, min(gx, cols - 1))
        gy = max(0, min(gy, rows - 1))

        # Update token position
        for token in bmap.tokens:
            if token.id == self._dragging:
                token.grid_x = gx
                token.grid_y = gy
                break
        self._redraw()

    def _on_double_click_damage(self, event):
        result = self._find_token_at_canvas(self._canvas.canvasx(event.x), self._canvas.canvasy(event.y))
        if not result or not result[0]:
            return
        self._change_hp(result[0])

    def _on_release(self, event):
        if self._dragging and self._current_map:
            self._cm.update_map(self._cid, self._current_map)
        self._dragging = None

    def _on_right_click(self, event):
        result = self._find_token_at_canvas(self._canvas.canvasx(event.x), self._canvas.canvasy(event.y))
        if not result or not result[0]:
            return
        token = result[0]
        menu = tk.Menu(self, tearoff=0, bg=C["bg_card"], fg=C["fg"],
                       activebackground=C["btn_hover"], activeforeground=C["fg"])
        menu.add_command(label=f"Damage/Heal '{token.name}'", command=lambda: self._change_hp(token))
        if token.is_down and token.token_type in {"player", "npc"}:
            menu.add_command(label="Death save SUCCESS", command=lambda: self._death_save(token, True))
            menu.add_command(label="Death save FAIL", command=lambda: self._death_save(token, False))
            menu.add_command(label="Stabilize / Revive to 1 HP", command=lambda: self._revive_token(token))
        menu.add_command(label=f"Delete '{token.name}'", command=lambda: self._remove_token(token))
        menu.tk_popup(event.x_root, event.y_root)

    def _change_hp(self, token):
        val = simpledialog.askinteger("HP Change", "Damage (positive) or heal (negative):",
                                      parent=self.winfo_toplevel(), initialvalue=1)
        if val is None:
            return
        token.current_hp = max(0, min(token.max_hp, token.current_hp - val))
        if token.current_hp <= 0:
            if token.token_type == "enemy":
                self._remove_token(token)
                return
            token.is_down = True
            token.death_success = 0
            token.death_fail = 0
        elif token.current_hp > 0:
            token.is_down = False
        self._cm.update_map(self._cid, self._current_map)
        self._redraw()

    def _death_save(self, token, success):
        if success:
            token.death_success = min(3, token.death_success + 1)
            if token.death_success >= 3:
                token.is_down = True
        else:
            token.death_fail = min(3, token.death_fail + 1)
            if token.death_fail >= 3:
                self._remove_token(token)
                return
        self._cm.update_map(self._cid, self._current_map)
        self._redraw()

    def _revive_token(self, token):
        token.current_hp = 1
        token.is_down = False
        token.death_success = 0
        token.death_fail = 0
        self._cm.update_map(self._cid, self._current_map)
        self._redraw()

    def _remove_token(self, token):
        if self._current_map:
            self._current_map.remove_token(token.id)
            self._turn_order = [tid for tid in self._turn_order if tid != token.id]
            if self._turn_order:
                self._turn_index = min(self._turn_index, len(self._turn_order) - 1)
            else:
                self._turn_index = 0
            self._cm.update_map(self._cid, self._current_map)
            self._update_turn_label()
            self._redraw()

    def _on_mousewheel(self, event):
        if event.state & 0x4:
            self._zoom = min(3.0, self._zoom * 1.1) if event.delta > 0 else max(0.3, self._zoom / 1.1)
            self._redraw()
        else:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


# ======================================================================
# Settings window
# ======================================================================
class SettingsWindow(tk.Toplevel):
    SETTINGS = [
        ("Ambient crossfade",
         "Duration of fade when switching between\n"
         "ambient tracks (ms)",
         "ambient_crossfade", "set_ambient_crossfade"),
        ("Ambient duck-out",
         "How fast ambient fades to silence\n"
         "when a stinger starts (ms)",
         "ambient_duck_out", "set_ambient_duck_out"),
        ("Ambient restore",
         "How fast ambient comes back\n"
         "after a stinger ends (ms)",
         "ambient_restore_in", "set_ambient_restore_in"),
        ("Stinger fade-in",
         "How fast the stinger fades in (ms)",
         "stinger_fade_in", "set_stinger_fade_in"),
        ("Stinger fade-out",
         "How fast the stinger fades out\n"
         "at the end (ms)",
         "stinger_fade_out", "set_stinger_fade_out"),
        ("Stop fade",
         "Fade duration when pressing\n"
         "any STOP button (ms)",
         "stop_fade", "set_stop_fade"),
    ]

    def __init__(self, parent, engine):
        super().__init__(parent)
        self.title("Settings")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._engine = engine
        self._entries = {}

        tk.Label(self, text="Audio Timing Settings",
                 bg=C["bg"], fg=C["accent"], font=FONT_TITLE
                 ).pack(padx=20, pady=(16, 8))
        tk.Label(self, text="All values are in milliseconds (1000 ms = 1 second)",
                 bg=C["bg"], fg=C["fg_dim"], font=FONT_TINY
                 ).pack(padx=20, pady=(0, 12))

        grid = tk.Frame(self, bg=C["bg"])
        grid.pack(padx=20, pady=(0, 12), fill="x")

        for row_idx, (label, desc, prop, _setter) in enumerate(self.SETTINGS):
            tk.Label(grid, text=label, bg=C["bg"], fg=C["fg"],
                     font=FONT_BOLD, anchor="w"
                     ).grid(row=row_idx * 2, column=0, sticky="w",
                            padx=(0, 16), pady=(8, 0))
            tk.Label(grid, text=desc, bg=C["bg"], fg=C["fg_dim"],
                     font=FONT_TINY, anchor="w", justify="left"
                     ).grid(row=row_idx * 2 + 1, column=0, sticky="w",
                            padx=(0, 16), pady=(0, 4))
            current_val = getattr(engine, prop)
            entry = tk.Entry(grid, width=8, bg=C["bg_entry"], fg=C["fg"],
                             insertbackground=C["fg"], font=FONT,
                             bd=1, relief="solid")
            entry.insert(0, str(current_val))
            entry.grid(row=row_idx * 2, column=1, rowspan=2,
                       sticky="e", padx=(0, 8), pady=4)
            tk.Label(grid, text="ms", bg=C["bg"], fg=C["fg_dim"],
                     font=FONT_SMALL
                     ).grid(row=row_idx * 2, column=2, rowspan=2,
                            sticky="w", pady=4)
            self._entries[prop] = entry

        grid.columnconfigure(0, weight=1)

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=20, pady=4)

        btn_frame = tk.Frame(self, bg=C["bg"])
        btn_frame.pack(padx=20, pady=(4, 16), fill="x")

        tk.Button(btn_frame, text="Reset to defaults", font=FONT_SMALL,
                  bg=C["bg_card"], fg=C["fg"], bd=0,
                  activebackground=C["btn_hover"], activeforeground=C["fg"],
                  cursor="hand2", padx=12, pady=6,
                  command=self._reset).pack(side="left")

        tk.Button(btn_frame, text="Apply & Close", font=FONT_SMALL,
                  bg=C["accent"], fg="#1e1e2e", bd=0,
                  activebackground=C["cat_active"], activeforeground="#1e1e2e",
                  cursor="hand2", padx=16, pady=6,
                  command=self._apply).pack(side="right")

        tk.Button(btn_frame, text="Cancel", font=FONT_SMALL,
                  bg=C["bg_card"], fg=C["fg"], bd=0,
                  activebackground=C["btn_hover"], activeforeground=C["fg"],
                  cursor="hand2", padx=12, pady=6,
                  command=self.destroy).pack(side="right", padx=(0, 8))

        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_x(), parent.winfo_y()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _apply(self):
        for _label, _desc, prop, setter in self.SETTINGS:
            entry = self._entries[prop]
            try:
                val = int(entry.get())
                if val < 0:
                    raise ValueError
                getattr(self._engine, setter)(val)
            except (ValueError, TypeError):
                messagebox.showerror(
                    "Invalid value",
                    f"'{entry.get()}' is not a valid value for {prop}.\n"
                    f"Please enter a positive integer (milliseconds).",
                    parent=self)
                entry.focus_set()
                return
        self.destroy()

    _DEFAULTS = {
        "ambient_crossfade": 2500,
        "ambient_duck_out": 2500,
        "ambient_restore_in": 2500,
        "stinger_fade_in": 2000,
        "stinger_fade_out": 2000,
        "stop_fade": 1500,
    }

    def _reset(self):
        for prop, default in self._DEFAULTS.items():
            entry = self._entries[prop]
            entry.delete(0, "end")
            entry.insert(0, str(default))


# ======================================================================
# Campaign Selector  (shown at startup and on switch)
# ======================================================================
class CampaignSelector(tk.Toplevel):
    def __init__(self, parent, campaign_mgr):
        super().__init__(parent)
        self._cm = campaign_mgr
        self._selected_id = None

        self.title("D&D Soundboard - Select Campaign")
        self.geometry("500x450")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.lift()
        self.focus_force()

        tk.Label(self, text="D&D Soundboard", bg=C["bg"], fg=C["accent"],
                 font=FONT_BIG).pack(pady=(24, 4))
        tk.Label(self, text="Select a campaign to start",
                 bg=C["bg"], fg=C["fg_dim"], font=FONT).pack(pady=(0, 16))

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=24, pady=4)

        self._list_frame = tk.Frame(self, bg=C["bg"])
        self._list_frame.pack(fill="both", expand=True, padx=24, pady=8)
        self._rebuild_list()

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=24, pady=4)

        btn_frame = tk.Frame(self, bg=C["bg"])
        btn_frame.pack(fill="x", padx=24, pady=(8, 20))

        tk.Button(btn_frame, text="+ New Campaign", font=FONT_BOLD,
                  bg=C["accent"], fg=C["bg"], bd=0,
                  activebackground=C["cat_active"], activeforeground=C["bg"],
                  cursor="hand2", padx=20, pady=10,
                  command=self._new_campaign).pack(side="left")

        tk.Button(btn_frame, text="Quit", font=FONT,
                  bg=C["btn_bg"], fg=C["fg"], bd=0,
                  activebackground=C["btn_hover"], activeforeground=C["fg"],
                  cursor="hand2", padx=16, pady=10,
                  command=self._on_close).pack(side="right")

    def _rebuild_list(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        campaigns = self._cm.all_campaigns()
        if not campaigns:
            tk.Label(self._list_frame,
                     text="No campaigns yet.\nCreate one to get started!",
                     bg=C["bg"], fg=C["fg_dim"], font=FONT,
                     justify="center").pack(expand=True)
            return
        for camp in campaigns:
            card = tk.Frame(self._list_frame, bg=C["bg_card"], cursor="hand2")
            card.pack(fill="x", pady=3, ipady=10)
            name_lbl = tk.Label(card, text=camp.name, bg=C["bg_card"],
                                fg=C["fg"], font=FONT_BOLD, anchor="w", padx=12)
            name_lbl.pack(fill="x", side="left", expand=True)
            desc_lbl = tk.Label(card, text=camp.description or "",
                                bg=C["bg_card"], fg=C["fg_dim"],
                                font=FONT_SMALL, anchor="e", padx=12)
            desc_lbl.pack(side="right")
            for w in (card, name_lbl, desc_lbl):
                w.bind("<Enter>", lambda e, c=card, n=name_lbl, d=desc_lbl:
                       [x.configure(bg=C["bg_card_hover"]) for x in (c, n, d)])
                w.bind("<Leave>", lambda e, c=card, n=name_lbl, d=desc_lbl:
                       [x.configure(bg=C["bg_card"]) for x in (c, n, d)])
                w.bind("<Button-1>", lambda e, cid=camp.id: self._select(cid))
                w.bind("<Button-3>", lambda e, cid=camp.id: self._right_click(e, cid))

    def _select(self, campaign_id):
        self._selected_id = campaign_id
        self.destroy()

    def _right_click(self, event, campaign_id):
        menu = tk.Menu(self, tearoff=0, bg=C["bg_card"], fg=C["fg"],
                       activebackground=C["btn_hover"], activeforeground=C["fg"])
        menu.add_command(label="Delete campaign",
                         command=lambda: self._delete_campaign(campaign_id))
        menu.tk_popup(event.x_root, event.y_root)

    def _delete_campaign(self, campaign_id):
        camp = self._cm.get_campaign(campaign_id)
        name = camp.name if camp else campaign_id
        if messagebox.askyesno("Confirm",
                               f"Delete campaign '{name}'?\n"
                               f"This will NOT delete audio files.",
                               parent=self):
            self._cm.delete_campaign(campaign_id)
            self._rebuild_list()

    def _new_campaign(self):
        name = simpledialog.askstring("New Campaign", "Campaign name:", parent=self)
        if not name or not name.strip():
            return
        desc = simpledialog.askstring("New Campaign",
                                      "Description (optional):", parent=self) or ""
        camp = self._cm.create_campaign(name.strip(), desc.strip())
        self._selected_id = camp.id
        self.destroy()

    def _on_close(self):
        self._selected_id = None
        self.destroy()

    @property
    def selected_id(self):
        return self._selected_id


# ======================================================================
# Main application window
# ======================================================================
class DnDSoundboard(TkinterDnD.Tk if HAS_DND else tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()

        self.title("D&D Soundboard")
        self.geometry("1300x750")
        self.minsize(1000, 600)
        self.configure(bg=C["bg"])

        # Style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar",
                         background=C["scrollbar"],
                         troughcolor=C["bg_panel"],
                         bordercolor=C["bg_panel"],
                         arrowcolor=C["fg_dim"])
        style.configure("TNotebook", background=C["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", background=C["btn_bg"],
                         foreground=C["fg"], padding=[16, 8],
                         font=FONT_BOLD)
        style.map("TNotebook.Tab",
                  background=[("selected", C["accent"])],
                  foreground=[("selected", C["bg"])])

        self._cm = CampaignManager()
        self._engine = MusicEngine()
        self._lib = None
        self._campaign_id = None

        # Show campaign selector
        if not self._select_campaign():
            self.destroy()
            return

        self.deiconify()

    def _select_campaign(self):
        """Show campaign selector. Returns True if a campaign was selected."""
        selector = CampaignSelector(self, self._cm)
        self.wait_window(selector)

        campaign_id = selector.selected_id
        if not campaign_id:
            return False

        self._campaign_id = campaign_id
        campaign = self._cm.get_campaign(campaign_id)
        self.title(f"D&D Soundboard - {campaign.name}")

        # Init library with campaign
        self._lib = Library(campaign_id=campaign_id)

        # Stop any playing audio
        self._engine.stop_all()

        # Pre-load tracks
        for t in self._lib.all_tracks():
            try:
                self._engine.load_track(t.name, self._lib.track_path(t))
            except Exception as e:
                logger.warning("Could not preload '%s': %s", t.name, e)

        self._build_ui(campaign_id)
        self.bind("<Key>", self._on_global_key)
        return True

    def _build_ui(self, campaign_id):
        # Destroy old content if switching campaigns
        for w in self.winfo_children():
            w.destroy()

        # Top bar
        top = tk.Frame(self, bg=C["bg"])
        top.pack(fill="x", padx=10, pady=(6, 2))

        campaign = self._cm.get_campaign(campaign_id)
        tk.Label(top, text=f"Campaign: {campaign.name}",
                 bg=C["bg"], fg=C["accent"], font=FONT_BOLD
                 ).pack(side="left")

        # Switch Campaign button
        make_button(top, "\u21C4 Switch Campaign", self._switch_campaign,
                    bg=C["btn_bg"], fg=C["fg"],
                    font=FONT_SMALL, padx=10, pady=4).pack(side="left", padx=(16, 0))

        make_button(top, "\u2699 Settings", self._open_settings,
                    bg=C["bg_card"], fg=C["fg"],
                    font=FONT_SMALL, padx=10, pady=4).pack(side="right")

        # Notebook with tabs
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=6, pady=(4, 6))

        # Soundboard tab
        self._soundboard = SoundboardTab(self._notebook, self._lib, self._engine)
        self._notebook.add(self._soundboard, text="  Soundboard  ")

        # Characters tab
        self._characters = CharactersTab(self._notebook, self._cm, campaign_id)
        self._notebook.add(self._characters, text="  Characters  ")

        # Battle Map tab
        self._battle_map = BattleMapTab(self._notebook, self._cm, campaign_id)
        self._notebook.add(self._battle_map, text="  Battle Map  ")

    def _open_settings(self):
        SettingsWindow(self, self._engine)

    def _switch_campaign(self):
        """Stop audio, show campaign selector, rebuild UI."""
        self._engine.stop_all()
        # Hide main window during selection
        self.withdraw()
        if self._select_campaign():
            self.deiconify()
        else:
            # User cancelled — restore previous state
            self.deiconify()

    def _on_global_key(self, event):
        # Never handle modified/system shortcuts in the soundboard handler.
        modifier_mask = 0x4 | 0x8 | 0x20000  # Ctrl / Alt / Command(Mac)
        if event.state & modifier_mask:
            return

        # Extra guard: control characters (e.g. Ctrl+V sends ) can appear
        # with unreliable state flags after focus/minimize changes on some systems.
        if event.char and ord(event.char) < 32:
        # Do not consume standard shortcuts like Ctrl+V/C/X, Alt+*, Cmd+*.
            return

        w = event.widget
        if isinstance(w, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text)):
            return
        self._soundboard.handle_hotkey(event.keysym)


# ======================================================================
# Entry point
# ======================================================================
if __name__ == "__main__":
    app = DnDSoundboard()
    app.mainloop()
