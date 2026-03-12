import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from app_settings import AppSettings
from campaign import CampaignManager
from library import Library
from localization import set_language, t

from .battle_map import BattleMapTab
from .characters import CharactersTab
from .common import BaseTk, C, FONT_BOLD, FONT_SMALL, logger, make_button
from .dialogs import CampaignSelector, SettingsWindow
from .soundboard import SoundboardTab

if TYPE_CHECKING:
    from audio_engine import MusicEngine


class DnDSoundboard(BaseTk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self._settings = AppSettings()
        set_language(self._settings.language)

        self.title(t("app.window_title"))
        self.geometry("1300x750")
        self.minsize(1000, 600)
        self.configure(bg=C["bg"])

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar", background=C["scrollbar"], troughcolor=C["bg_panel"], bordercolor=C["bg_panel"], arrowcolor=C["fg_dim"])
        style.configure("TNotebook", background=C["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", background=C["btn_bg"], foreground=C["fg"], padding=[16, 8], font=FONT_BOLD)
        style.map("TNotebook.Tab", background=[("selected", C["accent"])], foreground=[("selected", C["bg"])])

        self._cm = CampaignManager()
        self._engine: MusicEngine | None = None
        self._lib = None
        self._campaign_id = None
        self._warmup_after_id: str | None = None

        if not self._select_campaign():
            self.destroy()
            return

        self.deiconify()

    def _ensure_engine(self):
        if self._engine is None:
            from audio_engine import MusicEngine

            self._engine = MusicEngine()
        return self._engine

    def _select_campaign(self):
        selector = CampaignSelector(self, self._cm)
        self.wait_window(selector)

        campaign_id = selector.selected_id
        if not campaign_id:
            return False

        self._campaign_id = campaign_id
        campaign = self._cm.get_campaign(campaign_id)
        self.title(t("app.window_title_campaign", name=campaign.name))

        self._lib = Library(campaign_id=campaign_id)
        engine = self._ensure_engine()
        engine.stop_all()
        engine.clear_tracks()

        for track in self._lib.all_tracks():
            try:
                engine.load_track(track.name, self._lib.track_path(track))
            except Exception as ex:
                logger.warning("Could not register '%s': %s", track.name, ex)

        self._build_ui(campaign_id)
        self.bind("<Key>", self._on_global_key)
        self._schedule_warmup()
        return True

    def _schedule_warmup(self):
        self._cancel_warmup_schedule()
        if self._lib is None or self._engine is None:
            return
        track_names = [track.name for track in self._lib.all_tracks()]
        if not track_names:
            return
        self._warmup_after_id = self.after(300, lambda names=track_names: self._start_warmup(names))

    def _start_warmup(self, track_names):
        self._warmup_after_id = None
        if self._engine is None:
            return
        self._engine.warmup_tracks(track_names)

    def _cancel_warmup_schedule(self):
        if self._warmup_after_id is None:
            return
        try:
            self.after_cancel(self._warmup_after_id)
        except ValueError:
            pass
        self._warmup_after_id = None

    def _build_ui(self, campaign_id):
        selected_tab = None
        if hasattr(self, "_notebook"):
            try:
                selected_tab = self._notebook.index(self._notebook.select())
            except tk.TclError:
                selected_tab = None
        for widget in self.winfo_children():
            widget.destroy()

        top = tk.Frame(self, bg=C["bg"])
        top.pack(fill="x", padx=10, pady=(6, 2))

        campaign = self._cm.get_campaign(campaign_id)
        tk.Label(top, text=t("app.campaign_label", name=campaign.name), bg=C["bg"], fg=C["accent"], font=FONT_BOLD).pack(side="left")

        make_button(top, t("app.switch_campaign"), self._switch_campaign, bg=C["btn_bg"], fg=C["fg"], font=FONT_SMALL, padx=10, pady=4).pack(side="left", padx=(16, 0))
        make_button(top, t("app.settings"), self._open_settings, bg=C["bg_card"], fg=C["fg"], font=FONT_SMALL, padx=10, pady=4).pack(side="right")

        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=6, pady=(4, 6))

        self._soundboard = SoundboardTab(self._notebook, self._lib, self._ensure_engine())
        self._notebook.add(self._soundboard, text=t("tabs.soundboard"))

        self._characters = CharactersTab(self._notebook, self._cm, campaign_id)
        self._notebook.add(self._characters, text=t("tabs.characters"))

        self._battle_map = BattleMapTab(self._notebook, self._cm, campaign_id, self._lib, self._soundboard)
        self._notebook.add(self._battle_map, text=t("tabs.battle_map"))
        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        if selected_tab is not None and selected_tab < len(self._notebook.tabs()):
            self._notebook.select(selected_tab)

    def _open_settings(self):
        SettingsWindow(self, self._ensure_engine(), self._settings, on_apply=self._refresh_language)

    def _refresh_language(self):
        set_language(self._settings.language)
        if self._campaign_id:
            campaign = self._cm.get_campaign(self._campaign_id)
            if campaign:
                self.title(t("app.window_title_campaign", name=campaign.name))
            self._build_ui(self._campaign_id)

    def _switch_campaign(self):
        self._cancel_warmup_schedule()
        if self._engine is not None:
            self._engine.cancel_warmup()
            self._engine.stop_all()
        self.withdraw()
        self._select_campaign()
        self.deiconify()

    def _on_global_key(self, event):
        modifier_mask = 0x4 | 0x8 | 0x20000
        if event.state & modifier_mask:
            return
        if event.char and ord(event.char) < 32:
            return
        widget = event.widget
        if isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text)):
            return
        self._soundboard.handle_hotkey(event.keysym)

    def _on_tab_changed(self, event):
        selected_tab = event.widget.select()
        if selected_tab == str(self._battle_map):
            self._battle_map.refresh_audio_controls()
