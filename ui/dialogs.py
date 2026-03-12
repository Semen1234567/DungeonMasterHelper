import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from localization import language_options, set_language, t

from .common import C, FONT, FONT_BIG, FONT_BOLD, FONT_SMALL, FONT_TINY, FONT_TITLE


class SettingsWindow(tk.Toplevel):
    SETTINGS = [
        ("dialogs.settings.ambient_crossfade.label", "dialogs.settings.ambient_crossfade.description", "ambient_crossfade", "set_ambient_crossfade"),
        ("dialogs.settings.ambient_duck_out.label", "dialogs.settings.ambient_duck_out.description", "ambient_duck_out", "set_ambient_duck_out"),
        ("dialogs.settings.ambient_restore_in.label", "dialogs.settings.ambient_restore_in.description", "ambient_restore_in", "set_ambient_restore_in"),
        ("dialogs.settings.stinger_fade_in.label", "dialogs.settings.stinger_fade_in.description", "stinger_fade_in", "set_stinger_fade_in"),
        ("dialogs.settings.stinger_fade_out.label", "dialogs.settings.stinger_fade_out.description", "stinger_fade_out", "set_stinger_fade_out"),
        ("dialogs.settings.stop_fade.label", "dialogs.settings.stop_fade.description", "stop_fade", "set_stop_fade"),
    ]

    _DEFAULTS = {
        "ambient_crossfade": 2500,
        "ambient_duck_out": 2500,
        "ambient_restore_in": 2500,
        "stinger_fade_in": 2000,
        "stinger_fade_out": 2000,
        "stop_fade": 1500,
    }

    def __init__(self, parent, engine, settings, on_apply=None):
        super().__init__(parent)
        self.title(t("dialogs.settings.title"))
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._engine = engine
        self._settings = settings
        self._on_apply = on_apply
        self._entries = {}
        self._language_by_label = {label: code for code, label in language_options()}
        current_language = settings.language
        current_label = next((label for code, label in language_options() if code == current_language), current_language)
        self._language_var = tk.StringVar(value=current_label)

        tk.Label(self, text=t("dialogs.settings.header"), bg=C["bg"], fg=C["accent"], font=FONT_TITLE).pack(padx=20, pady=(16, 8))
        tk.Label(self, text=t("dialogs.settings.subheader"), bg=C["bg"], fg=C["fg_dim"], font=FONT_TINY).pack(padx=20, pady=(0, 6))

        lang_frame = tk.Frame(self, bg=C["bg"])
        lang_frame.pack(fill="x", padx=20, pady=(0, 12))
        tk.Label(lang_frame, text=t("dialogs.settings.interface_language"), bg=C["bg"], fg=C["fg"], font=FONT_BOLD, anchor="w").pack(fill="x")
        ttk.Combobox(lang_frame, textvariable=self._language_var, values=list(self._language_by_label), state="readonly").pack(fill="x", pady=(4, 4))
        tk.Label(lang_frame, text=t("dialogs.settings.interface_language_hint"), bg=C["bg"], fg=C["fg_dim"], font=FONT_TINY, anchor="w", justify="left", wraplength=440).pack(fill="x")

        grid = tk.Frame(self, bg=C["bg"])
        grid.pack(padx=20, pady=(0, 12), fill="x")

        for row_index, (label_key, description_key, prop, _setter) in enumerate(self.SETTINGS):
            tk.Label(grid, text=t(label_key), bg=C["bg"], fg=C["fg"], font=FONT_BOLD, anchor="w").grid(row=row_index * 2, column=0, sticky="w", padx=(0, 16), pady=(8, 0))
            tk.Label(grid, text=t(description_key), bg=C["bg"], fg=C["fg_dim"], font=FONT_TINY, anchor="w", justify="left").grid(row=row_index * 2 + 1, column=0, sticky="w", padx=(0, 16), pady=(0, 4))
            current_value = getattr(engine, prop)
            entry = tk.Entry(grid, width=8, bg=C["bg_entry"], fg=C["fg"], insertbackground=C["fg"], font=FONT, bd=1, relief="solid")
            entry.insert(0, str(current_value))
            entry.grid(row=row_index * 2, column=1, rowspan=2, sticky="e", padx=(0, 8), pady=4)
            tk.Label(grid, text=t("common.ms"), bg=C["bg"], fg=C["fg_dim"], font=FONT_SMALL).grid(row=row_index * 2, column=2, rowspan=2, sticky="w", pady=4)
            self._entries[prop] = entry

        grid.columnconfigure(0, weight=1)

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=20, pady=4)

        button_frame = tk.Frame(self, bg=C["bg"])
        button_frame.pack(padx=20, pady=(4, 16), fill="x")

        tk.Button(button_frame, text=t("dialogs.settings.reset_defaults"), font=FONT_SMALL, bg=C["bg_card"], fg=C["fg"], bd=0, activebackground=C["btn_hover"], activeforeground=C["fg"], cursor="hand2", padx=12, pady=6, command=self._reset).pack(side="left")
        tk.Button(button_frame, text=t("dialogs.settings.apply_close"), font=FONT_SMALL, bg=C["accent"], fg="#1e1e2e", bd=0, activebackground=C["cat_active"], activeforeground="#1e1e2e", cursor="hand2", padx=16, pady=6, command=self._apply).pack(side="right")
        tk.Button(button_frame, text=t("dialogs.settings.cancel"), font=FONT_SMALL, bg=C["bg_card"], fg=C["fg"], bd=0, activebackground=C["btn_hover"], activeforeground=C["fg"], cursor="hand2", padx=12, pady=6, command=self.destroy).pack(side="right", padx=(0, 8))

        self.update_idletasks()
        parent_width, parent_height = parent.winfo_width(), parent.winfo_height()
        parent_x, parent_y = parent.winfo_x(), parent.winfo_y()
        width, height = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{parent_x + (parent_width - width) // 2}+{parent_y + (parent_height - height) // 2}")

    def _apply(self):
        for label_key, _description, prop, setter in self.SETTINGS:
            entry = self._entries[prop]
            try:
                value = int(entry.get())
                if value < 0:
                    raise ValueError
                getattr(self._engine, setter)(value)
            except (ValueError, TypeError):
                messagebox.showerror(
                    t("dialogs.settings.invalid_value_title"),
                    t("dialogs.settings.invalid_value_message", value=entry.get(), setting=t(label_key)),
                    parent=self,
                )
                entry.focus_set()
                return
        language_code = self._language_by_label.get(self._language_var.get(), self._settings.language)
        self._settings.language = language_code
        self._settings.save()
        set_language(language_code)
        if self._on_apply:
            self._on_apply()
        self.destroy()

    def _reset(self):
        for prop, default in self._DEFAULTS.items():
            entry = self._entries[prop]
            entry.delete(0, "end")
            entry.insert(0, str(default))


class CampaignSelector(tk.Toplevel):
    def __init__(self, parent, campaign_mgr):
        super().__init__(parent)
        self._cm = campaign_mgr
        self._selected_id = None

        self.title(t("campaign_selector.window_title"))
        self.geometry("500x450")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.lift()
        self.focus_force()

        tk.Label(self, text=t("campaign_selector.header"), bg=C["bg"], fg=C["accent"], font=FONT_BIG).pack(pady=(24, 4))
        tk.Label(self, text=t("campaign_selector.subheader"), bg=C["bg"], fg=C["fg_dim"], font=FONT).pack(pady=(0, 16))

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=24, pady=4)

        self._list_frame = tk.Frame(self, bg=C["bg"])
        self._list_frame.pack(fill="both", expand=True, padx=24, pady=8)
        self._rebuild_list()

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=24, pady=4)

        button_frame = tk.Frame(self, bg=C["bg"])
        button_frame.pack(fill="x", padx=24, pady=(8, 20))

        tk.Button(button_frame, text=t("campaign_selector.new_campaign"), font=FONT_BOLD, bg=C["accent"], fg=C["bg"], bd=0, activebackground=C["cat_active"], activeforeground=C["bg"], cursor="hand2", padx=20, pady=10, command=self._new_campaign).pack(side="left")
        tk.Button(button_frame, text=t("campaign_selector.quit"), font=FONT, bg=C["btn_bg"], fg=C["fg"], bd=0, activebackground=C["btn_hover"], activeforeground=C["fg"], cursor="hand2", padx=16, pady=10, command=self._on_close).pack(side="right")

    def _rebuild_list(self):
        for widget in self._list_frame.winfo_children():
            widget.destroy()
        campaigns = self._cm.all_campaigns()
        if not campaigns:
            tk.Label(self._list_frame, text=t("campaign_selector.no_campaigns"), bg=C["bg"], fg=C["fg_dim"], font=FONT, justify="center").pack(expand=True)
            return
        for campaign in campaigns:
            card = tk.Frame(self._list_frame, bg=C["bg_card"], cursor="hand2")
            card.pack(fill="x", pady=3, ipady=10)
            name_label = tk.Label(card, text=campaign.name, bg=C["bg_card"], fg=C["fg"], font=FONT_BOLD, anchor="w", padx=12)
            name_label.pack(fill="x", side="left", expand=True)
            desc_label = tk.Label(card, text=campaign.description or "", bg=C["bg_card"], fg=C["fg_dim"], font=FONT_SMALL, anchor="e", padx=12)
            desc_label.pack(side="right")
            for widget in (card, name_label, desc_label):
                widget.bind("<Enter>", lambda e, c=card, n=name_label, d=desc_label: [x.configure(bg=C["bg_card_hover"]) for x in (c, n, d)])
                widget.bind("<Leave>", lambda e, c=card, n=name_label, d=desc_label: [x.configure(bg=C["bg_card"]) for x in (c, n, d)])
                widget.bind("<Button-1>", lambda e, campaign_id=campaign.id: self._select(campaign_id))
                widget.bind("<Button-3>", lambda e, campaign_id=campaign.id: self._right_click(e, campaign_id))

    def _select(self, campaign_id):
        self._selected_id = campaign_id
        self.destroy()

    def _right_click(self, event, campaign_id):
        menu = tk.Menu(self, tearoff=0, bg=C["bg_card"], fg=C["fg"], activebackground=C["btn_hover"], activeforeground=C["fg"])
        menu.add_command(label=t("campaign_selector.delete_campaign"), command=lambda: self._delete_campaign(campaign_id))
        menu.tk_popup(event.x_root, event.y_root)

    def _delete_campaign(self, campaign_id):
        campaign = self._cm.get_campaign(campaign_id)
        name = campaign.name if campaign else campaign_id
        if messagebox.askyesno(t("common.confirm"), t("campaign_selector.delete_campaign_confirm", name=name), parent=self):
            self._cm.delete_campaign(campaign_id)
            self._rebuild_list()

    def _new_campaign(self):
        name = simpledialog.askstring(t("campaign_selector.new_campaign_title"), t("campaign_selector.new_campaign_name"), parent=self)
        if not name or not name.strip():
            return
        description = simpledialog.askstring(t("campaign_selector.new_campaign_title"), t("campaign_selector.new_campaign_description"), parent=self) or ""
        campaign = self._cm.create_campaign(name.strip(), description.strip())
        self._selected_id = campaign.id
        self.destroy()

    def _on_close(self):
        self._selected_id = None
        self.destroy()

    @property
    def selected_id(self):
        return self._selected_id
