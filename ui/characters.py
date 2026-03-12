import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from campaign import Character, DEFAULT_STATS
from localization import ability_label, ability_tooltip, combat_stat_tooltip, t

from .common import C, FONT, FONT_BOLD, FONT_SMALL, FONT_STAT, FONT_TINY, FONT_TITLE, CategoryBar, attach_shared_tooltip, attach_tooltip, make_button


class CharacterEditor(tk.Toplevel):
    STAT_KEYS = ["str", "dex", "con", "int", "wis", "cha"]
    EXTRA_KEYS = ["ac", "hp", "speed", "cr"]

    def __init__(self, parent, campaign_mgr, campaign_id, character=None, char_type="enemy", category="", on_save=None):
        super().__init__(parent)
        self._cm = campaign_mgr
        self._cid = campaign_id
        self._char = character
        self._on_save = on_save
        self._is_new = character is None

        if self._is_new:
            self._char = Character(char_type=char_type, category=category)

        self.title(t("characters.editor.new_title") if self._is_new else t("characters.editor.edit_title"))
        self.geometry("700x750")
        self.configure(bg=C["bg"])
        self.transient(parent)
        self.grab_set()

        outer = tk.Frame(self, bg=C["bg"])
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=C["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)

        self._content = tk.Frame(canvas, bg=C["bg"])
        self._content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(canvas.find_withtag("all")[0], width=e.width - 20) if canvas.find_withtag("all") else None,
        )

        self._entries = {}
        self._build_form()

    def _make_section(self, title):
        tk.Label(self._content, text=title, bg=C["bg"], fg=C["accent"], font=FONT_BOLD, anchor="w").pack(fill="x", padx=16, pady=(12, 4))
        tk.Frame(self._content, bg=C["border"], height=1).pack(fill="x", padx=16, pady=(0, 4))

    def _make_field(self, label, key, default="", multiline=False, width=60):
        frame = tk.Frame(self._content, bg=C["bg"])
        frame.pack(fill="x", padx=16, pady=2)
        tk.Label(frame, text=label, bg=C["bg"], fg=C["fg_dim"], font=FONT_SMALL, width=14, anchor="w").pack(side="left")
        value = getattr(self._char, key, default) if not isinstance(default, dict) else default
        if multiline:
            text = tk.Text(frame, bg=C["bg_entry"], fg=C["fg"], insertbackground=C["fg"], font=FONT, height=4, width=width, bd=1, relief="solid", wrap="word")
            text.insert("1.0", value)
            text.pack(side="left", fill="x", expand=True, padx=(4, 0))
            self._entries[key] = text
        else:
            entry = tk.Entry(frame, bg=C["bg_entry"], fg=C["fg"], insertbackground=C["fg"], font=FONT, width=width, bd=1, relief="solid")
            entry.insert(0, value)
            entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
            self._entries[key] = entry

    def _build_form(self):
        self._make_section(t("characters.section.basic_info"))
        self._make_field(t("characters.field.name"), "name", self._char.name)

        frame = tk.Frame(self._content, bg=C["bg"])
        frame.pack(fill="x", padx=16, pady=2)
        tk.Label(frame, text=t("characters.field.type"), bg=C["bg"], fg=C["fg_dim"], font=FONT_SMALL, width=14, anchor="w").pack(side="left")
        self._type_var = tk.StringVar(value=self._char.char_type)
        for value, label in [("enemy", t("characters.type.enemy")), ("npc", t("characters.type.npc"))]:
            radio = tk.Radiobutton(frame, text=label, variable=self._type_var, value=value, bg=C["bg"], fg=C["fg"], selectcolor=C["bg_card"], activebackground=C["bg"], activeforeground=C["fg"], font=FONT_SMALL)
            radio.pack(side="left", padx=(4, 12))

        self._make_field(t("characters.field.category"), "category", self._char.category)

        self._make_section(t("characters.section.appearance_lore"))
        self._make_field(t("characters.field.appearance"), "appearance", self._char.appearance, multiline=True)
        self._make_field(t("characters.field.backstory"), "backstory", self._char.backstory, multiline=True)
        self._make_field(t("characters.field.weaknesses"), "weaknesses", self._char.weaknesses, multiline=True)

        self._make_section(t("characters.section.ability_scores"))
        stats_frame = tk.Frame(self._content, bg=C["bg"])
        stats_frame.pack(fill="x", padx=16, pady=4)
        for key in self.STAT_KEYS:
            column = tk.Frame(stats_frame, bg=C["bg_card"], padx=8, pady=6)
            column.pack(side="left", padx=4, pady=2)
            label = tk.Label(column, text=ability_label(key), bg=C["bg_card"], fg=C["accent"], font=FONT_BOLD)
            label.pack()
            value = self._char.stats.get(key, 10)
            entry = tk.Entry(column, bg=C["bg_entry"], fg=C["fg"], insertbackground=C["fg"], font=FONT_STAT, width=4, bd=1, relief="solid", justify="center")
            entry.insert(0, str(value))
            entry.pack(pady=(4, 2))
            modifier = (int(value) - 10) // 2
            modifier_text = f"+{modifier}" if modifier >= 0 else str(modifier)
            modifier_color = C["stat_high"] if modifier > 0 else (C["stat_low"] if modifier < 0 else C["fg_dim"])
            modifier_label = tk.Label(column, text=modifier_text, bg=C["bg_card"], fg=modifier_color, font=FONT_SMALL)
            modifier_label.pack()
            tooltip_text = ability_tooltip(key)
            attach_shared_tooltip((column, label, entry, modifier_label), tooltip_text)
            self._entries[f"stat_{key}"] = entry

        self._make_section(t("characters.section.combat_stats"))
        extra_frame = tk.Frame(self._content, bg=C["bg"])
        extra_frame.pack(fill="x", padx=16, pady=4)
        extra_labels = {
            "ac": t("characters.combat.ac"),
            "hp": t("characters.combat.hp"),
            "speed": t("characters.combat.speed"),
            "cr": t("characters.combat.cr"),
        }
        for key in self.EXTRA_KEYS:
            entry_frame = tk.Frame(extra_frame, bg=C["bg"])
            entry_frame.pack(side="left", padx=(0, 16))
            label = tk.Label(entry_frame, text=extra_labels[key], bg=C["bg"], fg=C["fg_dim"], font=FONT_SMALL)
            label.pack(side="left")
            value = str(self._char.stats.get(key, DEFAULT_STATS.get(key, "")))
            entry = tk.Entry(entry_frame, bg=C["bg_entry"], fg=C["fg"], insertbackground=C["fg"], font=FONT, width=8, bd=1, relief="solid")
            entry.insert(0, value)
            entry.pack(side="left", padx=(4, 0))
            tooltip_text = combat_stat_tooltip(key)
            attach_shared_tooltip((entry_frame, label, entry), tooltip_text)
            self._entries[f"stat_{key}"] = entry

        self._make_section(t("characters.section.abilities_actions"))
        self._make_field(t("characters.field.abilities"), "abilities", self._char.abilities, multiline=True)

        self._make_section(t("characters.section.dm_notes"))
        self._make_field(t("characters.field.notes"), "notes", self._char.notes, multiline=True)

        tk.Frame(self._content, bg=C["border"], height=1).pack(fill="x", padx=16, pady=(16, 8))
        button_frame = tk.Frame(self._content, bg=C["bg"])
        button_frame.pack(fill="x", padx=16, pady=(0, 16))

        tk.Button(button_frame, text=t("characters.save_character"), font=FONT_BOLD, bg=C["accent"], fg=C["bg"], bd=0, activebackground=C["cat_active"], activeforeground=C["bg"], cursor="hand2", padx=20, pady=8, command=self._save).pack(side="right")
        tk.Button(button_frame, text=t("characters.cancel"), font=FONT, bg=C["btn_bg"], fg=C["fg"], bd=0, activebackground=C["btn_hover"], activeforeground=C["fg"], cursor="hand2", padx=16, pady=8, command=self.destroy).pack(side="right", padx=(0, 8))

        if not self._is_new:
            tk.Button(button_frame, text=t("characters.delete"), font=FONT, bg=C["stop_bg"], fg=C["stop_fg"], bd=0, activebackground="#e06080", activeforeground=C["stop_fg"], cursor="hand2", padx=16, pady=8, command=self._delete).pack(side="left")

    def _collect_data(self):
        for key, widget in self._entries.items():
            if key.startswith("stat_"):
                continue
            value = widget.get("1.0", "end-1c").strip() if isinstance(widget, tk.Text) else widget.get().strip()
            setattr(self._char, key, value)
        self._char.char_type = self._type_var.get()
        stats = {}
        for key in self.STAT_KEYS + self.EXTRA_KEYS:
            entry = self._entries.get(f"stat_{key}")
            if not entry:
                continue
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
            messagebox.showwarning(t("characters.warning_title"), t("characters.name_required"), parent=self)
            return
        if not self._char.category:
            messagebox.showwarning(t("characters.warning_title"), t("characters.category_required"), parent=self)
            return
        self._cm.add_character(self._cid, self._char)
        if self._on_save:
            self._on_save()
        self.destroy()

    def _delete(self):
        if messagebox.askyesno(t("common.confirm"), t("characters.confirm_delete_character", name=self._char.name), parent=self):
            self._cm.remove_character(self._cid, self._char.id)
            if self._on_save:
                self._on_save()
            self.destroy()


class CharacterPanel(tk.Frame):
    def __init__(self, parent, char_type, char_type_label, campaign_mgr, campaign_id):
        super().__init__(parent, bg=C["bg_panel"], bd=0)
        self._char_type = char_type
        self._cm = campaign_mgr
        self._cid = campaign_id

        title_frame = tk.Frame(self, bg=C["bg_panel"])
        title_frame.pack(fill="x", padx=8, pady=(8, 2))
        tk.Label(title_frame, text=char_type_label, bg=C["bg_panel"], fg=C["accent"], font=FONT_TITLE).pack(side="left")
        make_button(title_frame, t("characters.add_character"), self._add_character, bg=C["accent3"], fg=C["bg"], font=FONT_SMALL, padx=8, pady=2).pack(side="right")

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=8, pady=4)

        self._cat_bar = CategoryBar(self, self._on_cat_select, self._on_add_category, add_label=t("characters.add_group"))
        self._cat_bar.pack(fill="x", padx=8, pady=(0, 4))

        container = tk.Frame(self, bg=C["bg_panel"])
        container.pack(fill="both", expand=True, padx=4, pady=4)

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
        self.refresh()

    def _on_canvas_resize(self, event):
        self._canvas.itemconfig(self._canvas_win, width=event.width)

    def _on_wheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def refresh(self):
        categories = self._cm.character_categories(self._cid, self._char_type)
        selected = self._cat_bar.selected
        self._cat_bar.set_categories(categories, selected)
        self._show_category(self._cat_bar.selected)

    def _show_category(self, category):
        for widget in self._inner.winfo_children():
            widget.destroy()
        if not category:
            return
        characters = self._cm.characters_in_category(self._cid, category, self._char_type)
        for character in characters:
            self._make_char_card(character)

    def _make_char_card(self, char):
        card = tk.Frame(self._inner, bg=C["bg_card"], cursor="hand2")
        card.pack(fill="x", padx=4, pady=3, ipady=8)

        icon_text = "\u2694" if char.char_type == "enemy" else "\u2655"
        icon_color = C["accent2"] if char.char_type == "enemy" else C["blue"]
        icon = tk.Label(card, text=icon_text, bg=C["bg_card"], fg=icon_color, font=("Segoe UI", 16), padx=8)
        icon.pack(side="left")

        info = tk.Frame(card, bg=C["bg_card"])
        info.pack(side="left", fill="x", expand=True, padx=4)
        name_label = tk.Label(info, text=char.name, bg=C["bg_card"], fg=C["fg"], font=FONT_BOLD, anchor="w")
        name_label.pack(fill="x")

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
            stat_line_label = tk.Label(info, text=stat_line, bg=C["bg_card"], fg=C["fg_dim"], font=FONT_TINY, anchor="w")
            stat_line_label.pack(fill="x")
            stat_line_tooltips = []
            if stats.get("hp"):
                stat_line_tooltips.append(f"HP: {combat_stat_tooltip('hp')}")
            if stats.get("ac"):
                stat_line_tooltips.append(f"AC: {combat_stat_tooltip('ac')}")
            if stats.get("cr"):
                stat_line_tooltips.append(f"CR: {combat_stat_tooltip('cr')}")
            if stat_line_tooltips:
                attach_tooltip(stat_line_label, "\n\n".join(stat_line_tooltips))

        scores_frame = tk.Frame(card, bg=C["bg_card"])
        scores_frame.pack(side="right", padx=8)
        for key in ["str", "dex", "con", "int", "wis", "cha"]:
            value = stats.get(key, 10)
            try:
                value_int = int(value)
            except (ValueError, TypeError):
                value_int = 10
            color = C["stat_high"] if value_int >= 14 else (C["stat_low"] if value_int <= 7 else C["fg_dim"])
            stat_label = tk.Label(scores_frame, text=f"{ability_label(key)} {value}", bg=C["bg_card"], fg=color, font=FONT_TINY, padx=3)
            stat_label.pack(side="left")
            attach_tooltip(stat_label, ability_tooltip(key))

        widgets = [card, icon, info, name_label, scores_frame]
        for widget in widgets:
            widget.bind("<Enter>", lambda e: [x.configure(bg=C["bg_card_hover"]) for x in widgets if isinstance(x, (tk.Frame, tk.Label))])
            widget.bind("<Leave>", lambda e: [x.configure(bg=C["bg_card"]) for x in widgets if isinstance(x, (tk.Frame, tk.Label))])
            widget.bind("<Button-1>", lambda e, c=char: self._edit_character(c))

    def _edit_character(self, char):
        CharacterEditor(self.winfo_toplevel(), self._cm, self._cid, character=char, on_save=self.refresh)

    def _add_character(self):
        category = self._cat_bar.selected or ""
        CharacterEditor(self.winfo_toplevel(), self._cm, self._cid, char_type=self._char_type, category=category, on_save=self.refresh)

    def _on_cat_select(self, cat):
        if isinstance(cat, tuple) and cat[0] == "__delete__":
            category_name = cat[1]
            characters = self._cm.characters_in_category(self._cid, category_name, self._char_type)
            if characters:
                if not messagebox.askyesno(t("common.confirm"), t("characters.confirm_delete_group", name=category_name, count=len(characters))):
                    return
                for character in characters:
                    self._cm.remove_character(self._cid, character.id)
            self.refresh()
            return
        self._show_category(cat)

    def _on_add_category(self):
        name = simpledialog.askstring(
            t("characters.new_group_title"),
            t("characters.new_group_prompt", kind=t(f"characters.type_plural.{self._char_type}")),
            parent=self.winfo_toplevel(),
        )
        if not name or not name.strip():
            return
        name = name.strip()
        categories = self._cm.character_categories(self._cid, self._char_type)
        if name not in categories:
            self._cat_bar.set_categories(categories + [name], name)
            self._show_category(name)
        else:
            self._cat_bar.set_categories(categories, name)
            self._show_category(name)


class CharactersTab(tk.Frame):
    def __init__(self, parent, campaign_mgr, campaign_id):
        super().__init__(parent, bg=C["bg"])
        panels = tk.Frame(self, bg=C["bg"])
        panels.pack(fill="both", expand=True, padx=10, pady=8)
        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=1)
        panels.rowconfigure(0, weight=1)

        self._enemies = CharacterPanel(panels, "enemy", t("characters.panel.enemies"), campaign_mgr, campaign_id)
        self._enemies.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self._npcs = CharacterPanel(panels, "npc", t("characters.panel.npcs"), campaign_mgr, campaign_id)
        self._npcs.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
