import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from campaign import MapToken
from combat_utils import hp_from_stats, initiative_from_dex
from localization import t

from .common import C, FONT_BOLD, FONT_SMALL, FONT_TINY, FONT_TITLE, HAS_PIL, IMAGE_EXTS, Image, ImageTk, logger, make_button, make_stop_button, make_volume_slider


class MapAudioDock(tk.Frame):
    def __init__(self, parent, library, audio_controls):
        super().__init__(parent, bg=C["bg_card"])
        self._lib = library
        self._audio = audio_controls
        self._selection_vars = {
            "ambient": tk.StringVar(value=""),
            "stinger": tk.StringVar(value=""),
            "fast_stinger": tk.StringVar(value=""),
        }
        self._combos = {}

        tk.Label(self, text=t("battle_map.audio_title"), bg=C["bg_card"], fg=C["accent"], font=FONT_BOLD).pack(anchor="w", padx=8, pady=(8, 2))
        tk.Label(
            self,
            textvariable=self._audio.status_var,
            bg=C["bg_card"],
            fg=C["fg"],
            font=FONT_SMALL,
            anchor="w",
            justify="left",
            wraplength=240,
        ).pack(fill="x", padx=8)

        self._make_now_playing_row(t("battle_map.audio.now_playing_ambient"), self._audio.ambient_now_var)
        self._make_now_playing_row(t("battle_map.audio.now_playing_stinger"), self._audio.stinger_now_var)
        self._make_now_playing_row(t("battle_map.audio.now_playing_fast"), self._audio.fast_now_var)

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=8, pady=6)

        self._make_selector(t("battle_map.audio.selector.ambient"), "ambient", stop_command=self._audio.stop_ambient)
        self._make_selector(t("battle_map.audio.selector.stinger"), "stinger", stop_command=self._audio.stop_stinger)
        self._make_selector(t("battle_map.audio.selector.fast"), "fast_stinger")

        controls = tk.Frame(self, bg=C["bg_card"])
        controls.pack(fill="x", padx=8, pady=(6, 4))
        make_volume_slider(controls, t("battle_map.audio.volume_ambient"), 80, self._audio.set_ambient_volume, variable=self._audio.ambient_volume_var, length=80, bg=C["bg_card"]).pack(anchor="w", pady=1)
        make_volume_slider(controls, t("battle_map.audio.volume_stinger"), 80, self._audio.set_stinger_volume, variable=self._audio.stinger_volume_var, length=80, bg=C["bg_card"]).pack(anchor="w", pady=1)
        make_volume_slider(controls, t("battle_map.audio.volume_fast"), 80, self._audio.set_fast_volume, variable=self._audio.fast_volume_var, length=80, bg=C["bg_card"]).pack(anchor="w", pady=1)

        make_stop_button(self, t("soundboard.stop_all"), self._audio.stop_all).pack(anchor="w", padx=8, pady=(4, 8))
        self.refresh_tracks()

    def _make_now_playing_row(self, label, variable):
        row = tk.Frame(self, bg=C["bg_card"])
        row.pack(fill="x", padx=8, pady=(2, 0))
        tk.Label(row, text=label, width=5, anchor="w", bg=C["bg_card"], fg=C["fg_dim"], font=FONT_TINY).pack(side="left")
        tk.Label(row, textvariable=variable, bg=C["bg_card"], fg=C["accent3"], font=FONT_TINY, anchor="w").pack(side="left", fill="x", expand=True)

    def _make_selector(self, title, kind, stop_command=None):
        block = tk.Frame(self, bg=C["bg_card"])
        block.pack(fill="x", padx=8, pady=(4, 0))

        top = tk.Frame(block, bg=C["bg_card"])
        top.pack(fill="x")
        tk.Label(top, text=title, bg=C["bg_card"], fg=C["fg"], font=FONT_SMALL).pack(side="left")
        make_button(top, t("battle_map.play"), lambda k=kind: self._play_selected(k), font=FONT_TINY, padx=6, pady=2).pack(side="right")
        if stop_command is not None:
            make_button(top, t("battle_map.stop"), stop_command, bg=C["stop_bg"], fg=C["stop_fg"], font=FONT_TINY, padx=6, pady=2).pack(side="right", padx=(0, 4))

        combo = ttk.Combobox(block, textvariable=self._selection_vars[kind], state="readonly")
        combo.pack(fill="x", pady=(2, 0))
        combo.bind("<Button-1>", lambda e, k=kind: self.refresh_tracks(preferred_kind=k))
        combo.bind("<<ComboboxSelected>>", lambda e, k=kind: self._sync_selection(k))
        self._combos[kind] = combo

    def _sync_selection(self, kind):
        value = self._selection_vars[kind].get()
        if not value:
            return
        self._selection_vars[kind].set(value)

    def _current_track_name(self, kind):
        if kind == "ambient":
            return self._audio.ambient_now_var.get()
        if kind == "stinger":
            return self._audio.stinger_now_var.get()
        return self._audio.fast_now_var.get()

    def refresh_tracks(self, preferred_kind=None):
        for kind, combo in self._combos.items():
            names = self._audio.track_names(kind)
            combo["values"] = names
            current = self._selection_vars[kind].get()
            preferred = self._current_track_name(kind) if kind == preferred_kind else ""
            if preferred and preferred in names:
                self._selection_vars[kind].set(preferred)
            elif current in names:
                self._selection_vars[kind].set(current)
            elif names:
                self._selection_vars[kind].set(names[0])
            else:
                self._selection_vars[kind].set("")

    def _play_selected(self, kind):
        self.refresh_tracks(preferred_kind=kind)
        self._audio.play_track_by_name(kind, self._selection_vars[kind].get())


class BattleMapTab(tk.Frame):
    """Interactive battle map with exploration/combat modes."""

    def __init__(self, parent, campaign_mgr, campaign_id, library, audio_controls):
        super().__init__(parent, bg=C["bg"])
        self._cm = campaign_mgr
        self._cid = campaign_id
        self._audio_controls = audio_controls
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

        tk.Label(toolbar, text=t("battle_map.title"), bg=C["bg"], fg=C["accent"], font=FONT_TITLE).pack(side="left")

        self._map_var = tk.StringVar(value=t("battle_map.select_map_placeholder"))
        self._map_combo = ttk.Combobox(toolbar, textvariable=self._map_var, state="readonly", width=25)
        self._map_combo.pack(side="left", padx=(16, 4))
        self._map_combo.bind("<<ComboboxSelected>>", self._on_map_selected)

        make_button(toolbar, t("battle_map.new_map"), self._new_map, bg=C["accent"], fg=C["bg"], font=FONT_SMALL, padx=8, pady=2).pack(side="left", padx=4)
        make_button(toolbar, t("battle_map.delete_map"), self._delete_map, bg=C["stop_bg"], fg=C["stop_fg"], font=FONT_SMALL, padx=8, pady=2).pack(side="left", padx=4)

        tk.Label(toolbar, text=t("battle_map.grid"), bg=C["bg"], fg=C["fg_dim"], font=FONT_SMALL).pack(side="left", padx=(16, 4))
        self._rows_var = tk.StringVar(value="20")
        self._cols_var = tk.StringVar(value="20")

        tk.Label(toolbar, text=t("battle_map.rows_short"), bg=C["bg"], fg=C["fg_dim"], font=FONT_TINY).pack(side="left")
        rows_entry = tk.Entry(toolbar, textvariable=self._rows_var, bg=C["bg_entry"], fg=C["fg"], insertbackground=C["fg"], font=FONT_SMALL, width=4, bd=1, relief="solid")
        rows_entry.pack(side="left", padx=(2, 4))
        rows_entry.bind("<Return>", lambda e: self._apply_grid())

        tk.Label(toolbar, text=t("battle_map.cols_short"), bg=C["bg"], fg=C["fg_dim"], font=FONT_TINY).pack(side="left")
        cols_entry = tk.Entry(toolbar, textvariable=self._cols_var, bg=C["bg_entry"], fg=C["fg"], insertbackground=C["fg"], font=FONT_SMALL, width=4, bd=1, relief="solid")
        cols_entry.pack(side="left", padx=(2, 4))
        cols_entry.bind("<Return>", lambda e: self._apply_grid())

        make_button(toolbar, t("battle_map.apply_grid"), self._apply_grid, font=FONT_SMALL, padx=6, pady=2).pack(side="left", padx=4)

        self._mode_btn = make_button(toolbar, t("battle_map.enter_combat"), self._toggle_mode, bg=C["accent2"], fg=C["bg"], font=FONT_SMALL, padx=8, pady=2)
        self._mode_btn.pack(side="left", padx=8)

        make_button(toolbar, t("battle_map.save"), self._save_map, bg=C["accent"], fg=C["bg"], font=FONT_SMALL, padx=8, pady=2).pack(side="right")

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

        side = tk.Frame(body, bg=C["bg_card"], width=270)
        side.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        side.grid_propagate(False)

        tk.Label(side, text=t("battle_map.characters"), bg=C["bg_card"], fg=C["accent"], font=FONT_BOLD).pack(anchor="w", padx=8, pady=(8, 2))
        self._char_list = tk.Listbox(side, bg=C["bg_panel"], fg=C["fg"], selectbackground=C["btn_hover"], height=7, relief="flat")
        self._char_list.pack(fill="x", padx=8)
        make_button(side, t("battle_map.place_selected"), self._add_selected_character_token, font=FONT_SMALL, padx=6, pady=2).pack(anchor="w", padx=8, pady=4)

        tk.Frame(side, bg=C["border"], height=1).pack(fill="x", padx=8, pady=4)
        tk.Label(side, text=t("battle_map.combat"), bg=C["bg_card"], fg=C["accent"], font=FONT_BOLD).pack(anchor="w", padx=8)
        self._turn_var = tk.StringVar(value=t("battle_map.turn_none"))
        tk.Label(side, textvariable=self._turn_var, bg=C["bg_card"], fg=C["fg"], font=FONT_SMALL, justify="left", wraplength=200).pack(anchor="w", padx=8, pady=(2, 2))
        self._turn_list = tk.Listbox(side, bg=C["bg_panel"], fg=C["fg"], selectbackground=C["btn_hover"], height=5, relief="flat")
        self._turn_list.pack(fill="x", padx=8, pady=(0, 4))
        make_button(side, t("battle_map.next_turn"), self._next_turn, font=FONT_SMALL, padx=6, pady=2).pack(anchor="w", padx=8, pady=2)
        make_button(side, t("battle_map.roll_initiative"), self._roll_initiative, font=FONT_SMALL, padx=6, pady=2).pack(anchor="w", padx=8, pady=2)

        tk.Frame(side, bg=C["border"], height=1).pack(fill="x", padx=8, pady=4)
        self._audio_dock = MapAudioDock(side, library, audio_controls)
        self._audio_dock.pack(fill="x", padx=0, pady=(0, 8))

        self._info_var = tk.StringVar(value=t("battle_map.no_map_loaded"))
        tk.Label(self, textvariable=self._info_var, bg=C["bg"], fg=C["fg_dim"], font=FONT_SMALL).pack(padx=10, pady=(0, 4))

        self._refresh_characters_list()
        self._refresh_map_list()

    def refresh_audio_controls(self):
        self._audio_dock.refresh_tracks()

    def _refresh_characters_list(self):
        self._characters = self._cm.load_characters(self._cid)
        self._char_list.delete(0, tk.END)
        for character in self._characters:
            self._char_list.insert(
                tk.END,
                t("battle_map.character_list_format", type=t(f"battle_map.token_type.{character.char_type}"), name=character.name),
            )

    def _get_token_by_id(self, token_id):
        if not self._current_map or not token_id:
            return None
        return next((token for token in self._current_map.tokens if token.id == token_id), None)

    def _sync_turn_order(self):
        if not self._current_map:
            self._turn_order = []
            self._turn_index = 0
            return None
        if not self._turn_order:
            self._turn_index = 0
            return None

        current_token_id = None
        if 0 <= self._turn_index < len(self._turn_order):
            current_token_id = self._turn_order[self._turn_index]

        existing_ids = {token.id for token in self._current_map.tokens}
        self._turn_order = [token_id for token_id in self._turn_order if token_id in existing_ids]
        if not self._turn_order:
            self._turn_index = 0
            return None
        if current_token_id in self._turn_order:
            self._turn_index = self._turn_order.index(current_token_id)
        else:
            self._turn_index = min(self._turn_index, len(self._turn_order) - 1)
        return self._turn_order[self._turn_index]

    def _active_turn_token_id(self):
        if not self._combat_mode:
            return None
        return self._sync_turn_order()

    def _health_badge_colors(self, token):
        if token.current_hp <= 0:
            return C["bg"], C["stat_low"]
        ratio = token.current_hp / max(1, token.max_hp)
        if ratio <= 0.33:
            return C["bg"], C["stat_low"]
        if ratio <= 0.66:
            return C["bg"], C["stat_mid"]
        return C["bg"], C["stat_high"]

    def _token_status_text(self, token):
        if token.token_type not in {"player", "npc"} or not token.is_down:
            return ""
        if token.death_success >= 3:
            return t("battle_map.token_status.stable")
        return t("battle_map.token_status.save", success=token.death_success)

    def _draw_text_badge(self, x, y, text, font, fg, bg, tags, anchor="s", outline=None):
        text_id = self._canvas.create_text(
            x,
            y,
            text=text,
            fill=fg,
            font=font,
            anchor=anchor,
            tags=tags,
        )
        bbox = self._canvas.bbox(text_id)
        if not bbox:
            return text_id
        rect_id = self._canvas.create_rectangle(
            bbox[0] - 4,
            bbox[1] - 2,
            bbox[2] + 4,
            bbox[3] + 2,
            fill=bg,
            outline=outline or bg,
            width=1,
            tags=tags,
        )
        self._canvas.tag_lower(rect_id, text_id)
        return text_id

    def _toggle_mode(self):
        self._combat_mode = not self._combat_mode
        if self._combat_mode:
            self._mode_btn.configure(text=t("battle_map.exit_combat"), bg=C["accent3"])
            self._roll_initiative()
        else:
            self._mode_btn.configure(text=t("battle_map.enter_combat"), bg=C["accent2"])
            self._turn_order = []
            self._turn_index = 0
            self._turn_var.set(t("battle_map.turn_none"))
            self._refresh_turn_order_view()
        self._redraw()

    def _refresh_map_list(self):
        maps = self._cm.load_maps(self._cid)
        names = [battle_map.name for battle_map in maps]
        self._map_combo["values"] = names
        if self._current_map and self._current_map.name not in names:
            self._current_map = None
            self._map_var.set(t("battle_map.select_map_placeholder"))

    def _on_map_selected(self, event=None):
        name = self._map_var.get()
        for battle_map in self._cm.load_maps(self._cid):
            if battle_map.name == name:
                self._current_map = battle_map
                self._rows_var.set(str(battle_map.grid_rows))
                self._cols_var.set(str(battle_map.grid_cols))
                self._load_map_image()
                self._refresh_characters_list()
                self._update_turn_label()
                self._redraw()
                return

    def _new_map(self):
        name = simpledialog.askstring(t("battle_map.new_map_title"), t("battle_map.new_map_name"), parent=self.winfo_toplevel())
        if not name or not name.strip():
            return
        path = filedialog.askopenfilename(title=t("battle_map.select_map_image"), filetypes=[("Images", " ".join(f"*{ext}" for ext in IMAGE_EXTS))])
        if not path:
            return
        rows = int(self._rows_var.get() or 20)
        cols = int(self._cols_var.get() or 20)
        battle_map = self._cm.add_map(self._cid, name.strip(), path, rows, cols)
        self._current_map = battle_map
        self._refresh_map_list()
        self._map_var.set(battle_map.name)
        self._load_map_image()
        self._redraw()

    def _delete_map(self):
        if not self._current_map:
            return
        if messagebox.askyesno(t("common.confirm"), t("battle_map.confirm_delete_map", name=self._current_map.name), parent=self.winfo_toplevel()):
            self._cm.remove_map(self._cid, self._current_map.id)
            self._current_map = None
            self._bg_image = None
            self._bg_photo = None
            self._canvas.delete("all")
            self._turn_order = []
            self._turn_index = 0
            self._turn_var.set(t("battle_map.turn_none"))
            self._refresh_turn_order_view()
            self._refresh_map_list()
            self._map_var.set(t("battle_map.select_map_placeholder"))
            self._info_var.set(t("battle_map.map_deleted"))

    def _save_map(self):
        if self._current_map:
            self._cm.update_map(self._cid, self._current_map)
            self._info_var.set(t("battle_map.map_saved", name=self._current_map.name))

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
                t(
                    "battle_map.map_info",
                    name=self._current_map.name,
                    width=self._bg_image.width,
                    height=self._bg_image.height,
                    rows=self._current_map.grid_rows,
                    cols=self._current_map.grid_cols,
                )
            )
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
        selection = self._char_list.curselection()
        if not selection:
            return
        character = self._characters[selection[0]]
        hp = hp_from_stats(character.stats, 10)
        token = MapToken(name=character.name, token_type=character.char_type, grid_x=0, grid_y=0, label=character.name[:2].upper(), character_id=character.id, max_hp=hp, current_hp=hp)
        self._current_map.add_token(token)
        self._cm.update_map(self._cid, self._current_map)
        self._redraw()

    def _roll_initiative(self):
        if not self._current_map:
            return
        characters_by_id = {character.id: character for character in self._characters}
        for token in self._current_map.tokens:
            dexterity = 10
            if token.character_id in characters_by_id:
                dexterity = int(characters_by_id[token.character_id].stats.get("dex", 10) or 10)
            token.initiative = initiative_from_dex(dexterity)
        self._turn_order = [token.id for token in sorted(self._current_map.tokens, key=lambda t: t.initiative, reverse=True)]
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
        token_id = self._sync_turn_order()
        if not token_id or not self._current_map:
            self._turn_var.set(t("battle_map.turn_none"))
            self._refresh_turn_order_view()
            return
        token = self._get_token_by_id(token_id)
        if token:
            status = f"HP {token.current_hp}/{token.max_hp}"
            extra_status = self._token_status_text(token)
            if extra_status:
                status += f", {extra_status}"
            self._turn_var.set(t("battle_map.turn_current", name=token.name, initiative=token.initiative, status=status))
        else:
            self._turn_var.set(t("battle_map.turn_none"))
        self._refresh_turn_order_view()

    def _refresh_turn_order_view(self):
        self._turn_list.delete(0, tk.END)
        self._sync_turn_order()
        if not self._current_map or not self._turn_order:
            return
        tokens_by_id = {token.id: token for token in self._current_map.tokens}
        for index, token_id in enumerate(self._turn_order):
            token = tokens_by_id.get(token_id)
            if not token:
                continue
            marker = "-> " if index == self._turn_index else "  "
            status = f"HP {token.current_hp}/{token.max_hp}"
            extra_status = self._token_status_text(token)
            if extra_status:
                status += f" {extra_status}"
            self._turn_list.insert(tk.END, f"{marker}{index + 1}. {token.name} ({token.initiative}) {status}")

    def _redraw(self):
        self._canvas.delete("all")
        if not self._current_map:
            return
        battle_map = self._current_map
        rows, cols = battle_map.grid_rows, battle_map.grid_cols
        if self._bg_image and HAS_PIL:
            image_width, image_height = self._bg_image.width, self._bg_image.height
            scaled_width = int(image_width * self._zoom)
            scaled_height = int(image_height * self._zoom)
            resized = self._bg_image.resize((scaled_width, scaled_height), Image.LANCZOS)
            self._bg_photo = ImageTk.PhotoImage(resized)
            self._canvas.create_image(0, 0, anchor="nw", image=self._bg_photo, tags="bg")
            canvas_width, canvas_height = scaled_width, scaled_height
        else:
            canvas_width = cols * 40
            canvas_height = rows * 40
            self._canvas.create_rectangle(0, 0, canvas_width, canvas_height, fill="#2a2a3a", outline="", tags="bg")

        self._canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))

        x_lines = [round(col * canvas_width / cols) for col in range(cols + 1)]
        y_lines = [round(row * canvas_height / rows) for row in range(rows + 1)]

        for y in y_lines:
            self._canvas.create_line(0, y, canvas_width, y, fill="#ffffff", width=1, tags="grid")
        for x in x_lines:
            self._canvas.create_line(x, 0, x, canvas_height, fill="#ffffff", width=1, tags="grid")

        active_token_id = self._active_turn_token_id()
        for token in battle_map.tokens:
            if token.id != active_token_id:
                self._draw_token(token, canvas_width, canvas_height, rows, cols)
        if active_token_id:
            active_token = self._get_token_by_id(active_token_id)
            if active_token:
                self._draw_token(active_token, canvas_width, canvas_height, rows, cols, is_active=True)

    def _draw_token(self, token, canvas_width, canvas_height, rows, cols, is_active=False):
        left = round(token.grid_x * canvas_width / cols)
        right = round((token.grid_x + 1) * canvas_width / cols)
        top = round(token.grid_y * canvas_height / rows)
        bottom = round((token.grid_y + 1) * canvas_height / rows)

        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        radius = min(right - left, bottom - top) * 0.4
        token_tags = (f"token_{token.id}", "token")

        if is_active:
            highlight_pad = max(4, int(radius * 0.3))
            self._canvas.create_oval(
                center_x - radius - highlight_pad,
                center_y - radius - highlight_pad,
                center_x + radius + highlight_pad,
                center_y + radius + highlight_pad,
                outline=C["amber"],
                width=3,
                tags=token_tags,
            )

        self._canvas.create_oval(
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
            fill=token.color,
            outline=C["amber"] if is_active else C["token_outline"],
            width=3 if is_active else 2,
            tags=token_tags,
        )
        self._canvas.create_text(
            center_x,
            center_y,
            text=token.label,
            fill=C["bg"],
            font=("Segoe UI", max(8, int(radius * 0.7)), "bold"),
            tags=token_tags,
        )
        meta_font = ("Segoe UI", max(7, int(radius * 0.34)), "bold")
        badge_outline = C["amber"] if is_active else C["border"]
        self._draw_text_badge(
            center_x,
            top - 24,
            token.name,
            meta_font,
            C["fg"],
            C["bg_panel"],
            token_tags,
            outline=badge_outline,
        )
        hp_fg, hp_bg = self._health_badge_colors(token)
        self._draw_text_badge(
            center_x,
            top - 6,
            f"HP {token.current_hp}/{token.max_hp}",
            meta_font,
            hp_fg,
            hp_bg,
            token_tags,
            outline=badge_outline,
        )
        status_text = self._token_status_text(token)
        if status_text:
            self._draw_text_badge(
                center_x,
                bottom + 6,
                status_text,
                meta_font,
                C["amber"],
                C["bg_panel"],
                token_tags,
                anchor="n",
                outline=badge_outline,
            )

    def _find_token_at_canvas(self, canvas_x, canvas_y):
        if not self._current_map:
            return None
        battle_map = self._current_map
        rows, cols = battle_map.grid_rows, battle_map.grid_cols
        if self._bg_image and HAS_PIL:
            canvas_width = int(self._bg_image.width * self._zoom)
            canvas_height = int(self._bg_image.height * self._zoom)
        else:
            canvas_width = cols * 40
            canvas_height = rows * 40

        grid_x = int(canvas_x * cols / canvas_width)
        grid_y = int(canvas_y * rows / canvas_height)
        grid_x = max(0, min(grid_x, cols - 1))
        grid_y = max(0, min(grid_y, rows - 1))
        return battle_map.get_token_at(grid_x, grid_y), grid_x, grid_y

    def _on_press(self, event):
        result = self._find_token_at_canvas(self._canvas.canvasx(event.x), self._canvas.canvasy(event.y))
        if result and result[0]:
            self._dragging = result[0].id

    def _on_drag(self, event):
        if not self._dragging or not self._current_map:
            return
        battle_map = self._current_map
        canvas_x = self._canvas.canvasx(event.x)
        canvas_y = self._canvas.canvasy(event.y)
        rows, cols = battle_map.grid_rows, battle_map.grid_cols
        if self._bg_image and HAS_PIL:
            canvas_width = int(self._bg_image.width * self._zoom)
            canvas_height = int(self._bg_image.height * self._zoom)
        else:
            canvas_width = cols * 40
            canvas_height = rows * 40

        grid_x = int(canvas_x * cols / canvas_width)
        grid_y = int(canvas_y * rows / canvas_height)
        grid_x = max(0, min(grid_x, cols - 1))
        grid_y = max(0, min(grid_y, rows - 1))

        for token in battle_map.tokens:
            if token.id == self._dragging:
                token.grid_x = grid_x
                token.grid_y = grid_y
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
        menu = tk.Menu(self, tearoff=0, bg=C["bg_card"], fg=C["fg"], activebackground=C["btn_hover"], activeforeground=C["fg"])
        menu.add_command(label=t("battle_map.menu.damage_heal", name=token.name), command=lambda: self._change_hp(token))
        if token.token_type in {"player", "npc"}:
            menu.add_command(label=t("battle_map.menu.mark_dead", name=token.name), command=lambda: self._mark_token_dead(token))
        if token.is_down and token.token_type in {"player", "npc"} and token.death_success < 3:
            next_success = min(3, token.death_success + 1)
            menu.add_command(label=t("battle_map.menu.death_save_success", success=next_success), command=lambda: self._death_save(token, True))
            menu.add_command(label=t("battle_map.menu.death_save_fail"), command=lambda: self._death_save(token, False))
        if token.is_down and token.token_type in {"player", "npc"}:
            menu.add_command(label=t("battle_map.menu.revive"), command=lambda: self._revive_token(token))
        menu.add_command(label=t("battle_map.menu.remove_from_map", name=token.name), command=lambda: self._remove_token(token))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _change_hp(self, token):
        value = simpledialog.askinteger(t("battle_map.hp_change_title"), t("battle_map.hp_change_prompt"), parent=self.winfo_toplevel(), initialvalue=1)
        if value is None:
            return
        self._apply_hp_change(token, value)

    def _apply_hp_change(self, token, value):
        token.current_hp = max(0, min(token.max_hp, token.current_hp - value))
        if token.current_hp <= 0:
            if token.token_type == "enemy":
                self._remove_token(token)
                return
            token.is_down = True
            token.death_success = 0
            token.death_fail = 0
        else:
            token.is_down = False
            token.death_success = 0
            token.death_fail = 0
        self._cm.update_map(self._cid, self._current_map)
        self._update_turn_label()
        self._redraw()

    def _death_save(self, token, success):
        if success:
            token.death_success = min(3, token.death_success + 1)
            token.death_fail = 0
        else:
            self._remove_token(token)
            return
        self._cm.update_map(self._cid, self._current_map)
        self._update_turn_label()
        self._redraw()

    def _revive_token(self, token):
        token.current_hp = 1
        token.is_down = False
        token.death_success = 0
        token.death_fail = 0
        self._cm.update_map(self._cid, self._current_map)
        self._update_turn_label()
        self._redraw()

    def _mark_token_dead(self, token):
        self._remove_token(token)

    def _remove_token(self, token):
        if not self._current_map:
            return
        removed_index = self._turn_order.index(token.id) if token.id in self._turn_order else -1
        current_token_id = self._turn_order[self._turn_index] if 0 <= self._turn_index < len(self._turn_order) else None
        self._current_map.remove_token(token.id)
        self._turn_order = [token_id for token_id in self._turn_order if token_id != token.id]
        if self._turn_order:
            if current_token_id == token.id:
                self._turn_index = removed_index % len(self._turn_order)
            elif 0 <= removed_index < self._turn_index:
                self._turn_index -= 1
            else:
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
            return
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
