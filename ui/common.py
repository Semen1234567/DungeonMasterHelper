import logging
import tkinter as tk
from tkinter import ttk

from localization import t

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    HAS_DND = True
    logger.info("tkinterdnd2 available -- drag & drop enabled")
except ImportError:
    DND_FILES = None
    TkinterDnD = None
    HAS_DND = False
    logger.info("tkinterdnd2 not found -- using file dialog fallback")

try:
    from PIL import Image, ImageTk

    HAS_PIL = True
    logger.info("Pillow available -- battle map images enabled")
except ImportError:
    Image = None
    ImageTk = None
    HAS_PIL = False
    logger.warning(
        "Pillow not found -- battle maps will have no background image. "
        "Install with: pip install Pillow"
    )

C = {
    "bg": "#1e1e2e",
    "bg_panel": "#282840",
    "bg_card": "#313150",
    "bg_card_hover": "#3b3b60",
    "bg_entry": "#3b3b60",
    "fg": "#cdd6f4",
    "fg_dim": "#6c7086",
    "accent": "#cba6f7",
    "accent2": "#f38ba8",
    "accent3": "#a6e3a1",
    "amber": "#f9e2af",
    "blue": "#89b4fa",
    "btn_bg": "#45475a",
    "btn_hover": "#585b70",
    "stop_bg": "#f38ba8",
    "stop_fg": "#1e1e2e",
    "cat_bg": "#45475a",
    "cat_active": "#cba6f7",
    "cat_active_fg": "#1e1e2e",
    "scrollbar": "#45475a",
    "border": "#45475a",
    "stat_high": "#a6e3a1",
    "stat_mid": "#f9e2af",
    "stat_low": "#f38ba8",
    "grid_line": "#ffffff30",
    "token_outline": "#1e1e2e",
}

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 13, "bold")
FONT_BIG = ("Segoe UI", 16, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_TINY = ("Segoe UI", 8)
FONT_STAT = ("Consolas", 12, "bold")

AUDIO_EXTS = {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".opus", ".aac", ".wma"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

BaseTk = TkinterDnD.Tk if HAS_DND and TkinterDnD is not None else tk.Tk


def make_button(parent, text, command, bg=None, fg=None, font=None, padx=10, pady=4, **kw):
    bg = bg or C["btn_bg"]
    fg = fg or C["fg"]
    font = font or FONT
    btn = tk.Label(
        parent,
        text=text,
        bg=bg,
        fg=fg,
        font=font,
        padx=padx,
        pady=pady,
        cursor="hand2",
        **kw,
    )
    btn.bind("<Button-1>", lambda e: command())
    btn.bind("<Enter>", lambda e: btn.configure(bg=C["btn_hover"]))
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
    return btn


def make_stop_button(parent, text, command):
    btn = tk.Label(
        parent,
        text=text,
        bg=C["stop_bg"],
        fg=C["stop_fg"],
        font=FONT_BOLD,
        padx=12,
        pady=4,
        cursor="hand2",
    )
    btn.bind("<Button-1>", lambda e: command())
    btn.bind("<Enter>", lambda e: btn.configure(bg="#e06080"))
    btn.bind("<Leave>", lambda e: btn.configure(bg=C["stop_bg"]))
    return btn


def make_volume_slider(parent, label, initial, command, variable=None, length=100, bg=None):
    bg = bg or C["bg"]
    frame = tk.Frame(parent, bg=bg)
    tk.Label(frame, text=label, bg=bg, fg=C["fg_dim"], font=FONT_TINY).pack(side="left", padx=(0, 2))
    scale = ttk.Scale(
        frame,
        from_=0,
        to=100,
        orient="horizontal",
        length=length,
        variable=variable,
        command=lambda v: command(float(v)),
    )
    if variable is None:
        scale.set(initial)
    scale.pack(side="left")
    return frame


class HoverTooltip:
    def __init__(self, widgets, text, delay=300, wraplength=320):
        if isinstance(widgets, (list, tuple, set)):
            self._widgets = [widget for widget in widgets if widget is not None]
        else:
            self._widgets = [widgets]
        self._widget = self._widgets[0]
        self._text = text
        self._delay = delay
        self._wraplength = wraplength
        self._after_id = None
        self._tip = None
        self._anchor_widget = self._widget
        for widget in self._widgets:
            widget.bind("<Enter>", self._schedule, add="+")
            widget.bind("<Leave>", self._schedule_hide, add="+")
            widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, event=None):
        if event is not None:
            self._anchor_widget = event.widget
        self._cancel()
        self._after_id = self._widget.after(self._delay, self._show)

    def _schedule_hide(self, _event=None):
        self._cancel()
        self._after_id = self._widget.after(40, self._hide_if_outside)

    def _cancel(self):
        if self._after_id is None:
            return
        try:
            self._widget.after_cancel(self._after_id)
        except ValueError:
            pass
        self._after_id = None

    def _pointer_widget(self):
        try:
            return self._widget.winfo_containing(self._widget.winfo_pointerx(), self._widget.winfo_pointery())
        except tk.TclError:
            return None

    def _belongs_to_group(self, widget):
        current = widget
        while current is not None:
            if current in self._widgets:
                return True
            try:
                parent_name = current.winfo_parent()
            except tk.TclError:
                return False
            if not parent_name:
                return False
            try:
                current = current.nametowidget(parent_name)
            except KeyError:
                return False
        return False

    def _hide_if_outside(self):
        self._after_id = None
        pointer_widget = self._pointer_widget()
        if pointer_widget is not None and self._belongs_to_group(pointer_widget):
            return
        self._hide_now()

    def _show(self):
        self._after_id = None
        if self._tip is not None or not self._text:
            return
        pointer_widget = self._pointer_widget()
        if pointer_widget is not None and self._belongs_to_group(pointer_widget):
            self._anchor_widget = pointer_widget
        anchor_widget = self._anchor_widget if self._anchor_widget is not None else self._widget
        self._tip = tk.Toplevel(anchor_widget)
        self._tip.wm_overrideredirect(True)
        self._tip.attributes("-topmost", True)
        x = anchor_widget.winfo_rootx() + 14
        y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + 8
        self._tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self._tip,
            text=self._text,
            justify="left",
            wraplength=self._wraplength,
            bg=C["bg_card"],
            fg=C["fg"],
            relief="solid",
            bd=1,
            padx=10,
            pady=6,
            font=FONT_SMALL,
        )
        label.pack()

    def _hide(self, _event=None):
        self._cancel()
        self._hide_now()

    def _hide_now(self):
        if self._tip is None:
            return
        self._tip.destroy()
        self._tip = None


def attach_tooltip(widget, text):
    widget._hover_tooltip = HoverTooltip(widget, text)
    return widget._hover_tooltip


def attach_shared_tooltip(widgets, text):
    tooltip = HoverTooltip(widgets, text)
    for widget in widgets:
        widget._hover_tooltip = tooltip
    return tooltip


class CategoryBar(tk.Frame):
    def __init__(self, parent, on_select, on_add_category, add_label=None):
        super().__init__(parent, bg=C["bg_panel"])
        self._on_select = on_select
        self._cats = []
        self._selected = None
        self._btns = []

        add_label = add_label or t("common.add_category")

        self._scroll = tk.Frame(self, bg=C["bg_panel"])
        self._scroll.pack(side="left", fill="x", expand=True)

        self._add_btn = make_button(
            self,
            add_label,
            on_add_category,
            bg=C["accent"],
            fg=C["bg"],
            font=FONT_SMALL,
            padx=8,
            pady=2,
        )
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
        for button in self._btns:
            button.destroy()
        self._btns.clear()
        for cat in self._cats:
            active = cat == self._selected
            bg = C["cat_active"] if active else C["cat_bg"]
            fg = C["cat_active_fg"] if active else C["fg"]
            label = tk.Label(
                self._scroll,
                text=cat,
                bg=bg,
                fg=fg,
                font=FONT_SMALL,
                padx=10,
                pady=3,
                cursor="hand2",
            )
            label.pack(side="left", padx=2, pady=2)
            label.bind("<Button-1>", lambda e, c=cat: self._click(c))
            label.bind("<Button-3>", lambda e, c=cat: self._right_click(e, c))
            self._btns.append(label)

    def _click(self, cat):
        self._selected = cat
        self._rebuild()
        self._on_select(cat)

    def _right_click(self, event, cat):
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=C["bg_card"],
            fg=C["fg"],
            activebackground=C["btn_hover"],
            activeforeground=C["fg"],
        )
        menu.add_command(label=t("common.delete_named", name=cat), command=lambda: self._on_select(("__delete__", cat)))
        menu.tk_popup(event.x_root, event.y_root)
