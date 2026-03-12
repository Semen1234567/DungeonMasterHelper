import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from localization import t

from .common import (
    AUDIO_EXTS,
    C,
    DND_FILES,
    FONT,
    FONT_BOLD,
    FONT_SMALL,
    FONT_TITLE,
    FONT_TINY,
    HAS_DND,
    CategoryBar,
    logger,
    make_button,
    make_stop_button,
    make_volume_slider,
)


class TrackList(tk.Frame):
    def __init__(self, parent, kind, library, engine, play_cb):
        super().__init__(parent, bg=C["bg_panel"])
        self._kind = kind
        self._lib = library
        self._engine = engine
        self._play_cb = play_cb
        self._category = None
        self._tracks = []

        header = tk.Frame(self, bg=C["bg_panel"])
        header.pack(fill="x", padx=4, pady=(4, 0))
        self._add_btn = make_button(header, t("soundboard.add_track"), self._add_track, font=FONT_SMALL, padx=8, pady=2)
        self._add_btn.pack(side="right")

        self._hint = tk.Label(self, text=t("soundboard.drag_drop_hint"), bg=C["bg_panel"], fg=C["fg_dim"], font=FONT_TINY)
        self._hint.pack(pady=(2, 0))

        container = tk.Frame(self, bg=C["bg_panel"])
        container.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(container, bg=C["bg_panel"], highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(container, orient="vertical", command=self._canvas.yview)
        self._inner = tk.Frame(self._canvas, bg=C["bg_panel"])
        self._inner.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas_win = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.pack(side="right", fill="y")

        self._canvas.bind("<Enter>", lambda e: self._canvas.bind_all("<MouseWheel>", self._on_wheel))
        self._canvas.bind("<Leave>", lambda e: self._canvas.unbind_all("<MouseWheel>"))

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
        for widget in self._inner.winfo_children():
            widget.destroy()
        if not self._category:
            return
        self._tracks = self._lib.tracks_in_category(self._category, self._kind)
        for track in self._tracks:
            self._make_track_card(track)

    def _make_track_card(self, track):
        if self._kind == "fast_stinger":
            self._make_fast_card(track)
            return

        card = tk.Frame(self._inner, bg=C["bg_card"], cursor="hand2")
        card.pack(fill="x", padx=4, pady=2, ipady=6)

        play_icon = tk.Label(card, text="\u25B6", bg=C["bg_card"], fg=C["accent3"], font=FONT, padx=8)
        play_icon.pack(side="left")

        name_label = tk.Label(card, text=track.name, bg=C["bg_card"], fg=C["fg"], font=FONT, anchor="w")
        name_label.pack(side="left", fill="x", expand=True, padx=4)

        for widget in (card, play_icon, name_label):
            widget.bind("<Enter>", lambda e: [x.configure(bg=C["bg_card_hover"]) for x in (card, play_icon, name_label)])
            widget.bind("<Leave>", lambda e: [x.configure(bg=C["bg_card"]) for x in (card, play_icon, name_label)])
            widget.bind("<Button-1>", lambda e, t=track: self._play(t))
            widget.bind("<Button-3>", lambda e, t=track: self._right_click_track(e, t))

    def _make_fast_card(self, track):
        hotkey = track.hotkey or "?"
        card = tk.Frame(self._inner, bg=C["amber"], cursor="hand2")
        card.pack(side="left", padx=4, pady=4, ipadx=8, ipady=6)

        tk.Label(card, text=track.name, bg=C["amber"], fg=C["bg"], font=FONT_SMALL).pack()
        tk.Label(card, text=f"[{hotkey}]", bg=C["amber"], fg=C["bg_card"], font=FONT_TINY).pack()

        card.bind("<Button-1>", lambda e, t=track: self._play(t))
        card.bind("<Button-3>", lambda e, t=track: self._right_click_fast(e, t))

    def _play(self, track):
        try:
            self._play_cb(track)
        except Exception as ex:
            logger.error("Play error: %s", ex)

    def _right_click_track(self, event, track):
        menu = tk.Menu(self, tearoff=0, bg=C["bg_card"], fg=C["fg"], activebackground=C["btn_hover"], activeforeground=C["fg"])
        menu.add_command(label=t("soundboard.menu.delete_track", name=track.name), command=lambda: self._delete_track(track))
        menu.tk_popup(event.x_root, event.y_root)

    def _right_click_fast(self, event, track):
        menu = tk.Menu(self, tearoff=0, bg=C["bg_card"], fg=C["fg"], activebackground=C["btn_hover"], activeforeground=C["fg"])
        menu.add_command(label=t("soundboard.menu.change_hotkey"), command=lambda: self._change_hotkey(track))
        menu.add_command(label=t("soundboard.menu.delete_track", name=track.name), command=lambda: self._delete_track(track))
        menu.tk_popup(event.x_root, event.y_root)

    def _change_hotkey(self, track):
        window = tk.Toplevel(self.winfo_toplevel())
        window.title(t("soundboard.hotkey_window_title"))
        window.geometry("260x100")
        window.configure(bg=C["bg"])
        window.transient(self.winfo_toplevel())
        window.grab_set()
        tk.Label(window, text=t("soundboard.hotkey_prompt"), bg=C["bg"], fg=C["fg"], font=FONT).pack(expand=True)

        def _capture(event):
            track.hotkey = event.keysym
            self._lib.update_hotkey(track.name, track.hotkey)
            window.destroy()
            self._refresh()

        window.bind("<Key>", _capture)
        window.focus_force()

    def _delete_track(self, track):
        self._lib.remove_track(track.name)
        self._engine.unload_track(track.name)
        self._refresh()

    def _add_track(self):
        if not self._category:
            messagebox.showinfo(t("soundboard.select_category_title"), t("soundboard.select_category_message"))
            return
        paths = filedialog.askopenfilenames(title=t("soundboard.select_audio_files"), filetypes=[("Audio", " ".join(f"*{ext}" for ext in AUDIO_EXTS))])
        for path in paths:
            self._import_file(path)

    def _import_file(self, path):
        if not self._category:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in AUDIO_EXTS:
            return
        name = os.path.splitext(os.path.basename(path))[0]
        hotkey = ""
        if self._kind == "fast_stinger":
            window = tk.Toplevel(self.winfo_toplevel())
            window.title(t("soundboard.assign_hotkey_title"))
            window.geometry("260x100")
            window.configure(bg=C["bg"])
            window.transient(self.winfo_toplevel())
            window.grab_set()
            tk.Label(window, text=t("soundboard.assign_hotkey_prompt"), bg=C["bg"], fg=C["fg"], font=FONT).pack(expand=True)
            result = {"key": ""}

            def _capture(event):
                if event.keysym != "Escape":
                    result["key"] = event.keysym
                window.destroy()

            window.bind("<Key>", _capture)
            window.focus_force()
            window.wait_window()
            hotkey = result["key"]

        track = self._lib.add_track(path, name, self._category, self._kind, hotkey=hotkey)
        try:
            self._engine.load_track(track.name, self._lib.track_path(track))
            self._engine.prepare_track(track.name)
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
        for path in paths:
            self._import_file(path)

    def handle_hotkey(self, keysym):
        if self._kind != "fast_stinger":
            return False
        for track in self._lib.all_tracks():
            if track.kind == "fast_stinger" and track.hotkey == keysym:
                self._play(track)
                return True
        return False


class SoundPanel(tk.Frame):
    def __init__(self, parent, title, kind, library, engine, play_cb, now_playing_var):
        super().__init__(parent, bg=C["bg_panel"], bd=0)
        self._kind = kind
        self._lib = library
        self._now_playing_var = now_playing_var

        title_frame = tk.Frame(self, bg=C["bg_panel"])
        title_frame.pack(fill="x", padx=8, pady=(8, 2))
        tk.Label(title_frame, text=title, bg=C["bg_panel"], fg=C["accent"], font=FONT_TITLE).pack(side="left")

        tk.Label(self, textvariable=self._now_playing_var, bg=C["bg_panel"], fg=C["accent3"], font=FONT_SMALL, anchor="w").pack(fill="x", padx=12, pady=(0, 2))

        self._cat_bar = CategoryBar(self, self._on_cat_select, self._on_add_category)
        self._cat_bar.pack(fill="x", padx=8, pady=(0, 4))

        self._track_view = TrackList(self, kind, library, engine, play_cb)
        self._track_view.pack(fill="both", expand=True, padx=4, pady=4)

        self.refresh()

    def refresh(self):
        categories = self._lib.categories(self._kind)
        selected = self._cat_bar.selected
        self._cat_bar.set_categories(categories, selected)
        if self._cat_bar.selected:
            self._track_view.show_category(self._cat_bar.selected)

    def _on_cat_select(self, cat):
        if isinstance(cat, tuple) and cat[0] == "__delete__":
            category_name = cat[1]
            tracks = self._lib.tracks_in_category(category_name, self._kind)
            if tracks:
                if not messagebox.askyesno(t("common.confirm"), t("soundboard.confirm_delete_category", name=category_name, count=len(tracks))):
                    return
                for track in tracks:
                    self._lib.remove_track(track.name)
            self.refresh()
            return
        self._track_view.show_category(cat)

    def _on_add_category(self):
        name = simpledialog.askstring(
            t("soundboard.new_category_title"),
            t("soundboard.new_category_prompt", kind=t(f"soundboard.kind_label.{self._kind}")),
            parent=self.winfo_toplevel(),
        )
        if not name or not name.strip():
            return
        name = name.strip()
        categories = self._lib.categories(self._kind)
        if name not in categories:
            self._cat_bar.set_categories(categories + [name], name)
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


class SoundboardTab(tk.Frame):
    def __init__(self, parent, library, engine):
        super().__init__(parent, bg=C["bg"])
        self._lib = library
        self._engine = engine
        self._status_var = tk.StringVar(value=t("soundboard.status.nothing_playing"))
        self._ambient_now_var = tk.StringVar(value="")
        self._stinger_now_var = tk.StringVar(value="")
        self._fast_now_var = tk.StringVar(value="")
        self._ambient_volume_var = tk.DoubleVar(value=80.0)
        self._stinger_volume_var = tk.DoubleVar(value=80.0)
        self._fast_volume_var = tk.DoubleVar(value=80.0)

        top = tk.Frame(self, bg=C["bg"], height=48)
        top.pack(fill="x", padx=10, pady=(8, 4))

        tk.Label(top, textvariable=self._status_var, bg=C["bg"], fg=C["fg"], font=FONT_BOLD, anchor="w").pack(side="left", fill="x", expand=True)

        make_volume_slider(top, t("soundboard.volume.ambient_short"), 80, self._on_vol_amb, variable=self._ambient_volume_var).pack(side="left", padx=4)
        engine.set_ambient_volume(self._ambient_volume_var.get() / 100.0)
        make_volume_slider(top, t("soundboard.volume.stinger_short"), 80, self._on_vol_stng, variable=self._stinger_volume_var).pack(side="left", padx=4)
        engine.set_stinger_volume(self._stinger_volume_var.get() / 100.0)
        make_volume_slider(top, t("soundboard.volume.fast_short"), 80, self._on_vol_fast, variable=self._fast_volume_var).pack(side="left", padx=4)
        engine.set_fast_stinger_volume(self._fast_volume_var.get() / 100.0)

        make_stop_button(top, t("soundboard.stop_all"), self._on_stop_all).pack(side="right", padx=(4, 0))
        make_stop_button(top, t("soundboard.stop_stinger"), self._on_stop_stinger).pack(side="right", padx=4)
        make_stop_button(top, t("soundboard.stop_ambient"), self._on_stop_ambient).pack(side="right", padx=4)

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=10)

        panels = tk.Frame(self, bg=C["bg"])
        panels.pack(fill="both", expand=True, padx=10, pady=8)
        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=1)
        panels.columnconfigure(2, weight=1)
        panels.rowconfigure(0, weight=1)

        self._p_ambient = SoundPanel(panels, t("soundboard.panel.ambient"), "ambient", library, engine, self.play_track, self._ambient_now_var)
        self._p_ambient.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self._p_stinger = SoundPanel(panels, t("soundboard.panel.stingers"), "stinger", library, engine, self.play_track, self._stinger_now_var)
        self._p_stinger.grid(row=0, column=1, sticky="nsew", padx=4)

        self._p_fast = SoundPanel(panels, t("soundboard.panel.fast_stingers"), "fast_stinger", library, engine, self.play_track, self._fast_now_var)
        self._p_fast.grid(row=0, column=2, sticky="nsew", padx=(4, 0))

    @property
    def status_var(self):
        return self._status_var

    @property
    def ambient_now_var(self):
        return self._ambient_now_var

    @property
    def stinger_now_var(self):
        return self._stinger_now_var

    @property
    def fast_now_var(self):
        return self._fast_now_var

    @property
    def ambient_volume_var(self):
        return self._ambient_volume_var

    @property
    def stinger_volume_var(self):
        return self._stinger_volume_var

    @property
    def fast_volume_var(self):
        return self._fast_volume_var

    def set_ambient_volume(self, val):
        self._on_vol_amb(val)

    def set_stinger_volume(self, val):
        self._on_vol_stng(val)

    def set_fast_volume(self, val):
        self._on_vol_fast(val)

    def track_names(self, kind):
        return sorted((track.name for track in self._lib.all_tracks() if track.kind == kind), key=str.lower)

    def play_track_by_name(self, kind, name):
        if not name:
            return False
        track = self._lib.get_track(name)
        if track is None or track.kind != kind:
            return False
        self.play_track(track)
        return True

    def play_track(self, track):
        if track.kind == "ambient":
            self._engine.play_ambient(track.name)
            self._status_var.set(t("soundboard.status.ambient_playing", name=track.name))
            self._ambient_now_var.set(track.name)
        elif track.kind == "stinger":
            self._engine.play_stinger(track.name)
            self._status_var.set(t("soundboard.status.stinger_playing", name=track.name))
            self._stinger_now_var.set(track.name)
        elif track.kind == "fast_stinger":
            self._engine.play_fast_stinger(track.name)
            self._status_var.set(t("soundboard.status.fast_playing", name=track.name))
            self._fast_now_var.set(track.name)

    def _on_vol_amb(self, val):
        self._engine.set_ambient_volume(val / 100.0)

    def _on_vol_stng(self, val):
        self._engine.set_stinger_volume(val / 100.0)

    def _on_vol_fast(self, val):
        self._engine.set_fast_stinger_volume(val / 100.0)

    def _on_stop_all(self):
        self._engine.stop_all()
        self._status_var.set(t("soundboard.status.stopped"))
        self._ambient_now_var.set("")
        self._stinger_now_var.set("")
        self._fast_now_var.set("")

    def _on_stop_ambient(self):
        self._engine.stop_ambient()
        self._status_var.set(t("soundboard.status.ambient_stopped"))
        self._ambient_now_var.set("")

    def _on_stop_stinger(self):
        self._engine.stop_stinger()
        self._status_var.set(t("soundboard.status.stinger_stopped"))
        self._stinger_now_var.set("")

    def stop_all(self):
        self._on_stop_all()

    def stop_ambient(self):
        self._on_stop_ambient()

    def stop_stinger(self):
        self._on_stop_stinger()

    def handle_hotkey(self, keysym):
        fast_panel = self._p_fast.fast_panel
        if fast_panel:
            return fast_panel.handle_hotkey(keysym)
        return False
