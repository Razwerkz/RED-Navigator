"""
Shim module for EDMC's myNotebook module.
Provides tkinter widgets that EDMC plugins expect.
"""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable
from collections.abc import Callable as AbcCallable

# Platform-specific colors
if sys.platform == 'win32':
    PAGEFG = 'SystemWindowText'
    PAGEBG = 'SystemWindow'
else:
    PAGEFG = None
    PAGEBG = None

try:
    from l10n import translations as tr
except ImportError:
    class _DummyTranslations:
        def tl(self, text: str) -> str:
            return text
    tr = _DummyTranslations()

class Notebook(ttk.Notebook):
    """Custom ttk.Notebook class to fix some display issues."""
    def __init__(self, master: Any = None, **kw):
        super().__init__(master, **kw)
        style = ttk.Style()
        if sys.platform == 'win32':
            style.configure('nb.TFrame', background=PAGEBG)
            style.configure('nb.TButton', background=PAGEBG)
            style.configure('nb.TCheckbutton', foreground=PAGEFG, background=PAGEBG)
            style.configure('nb.TMenubutton', foreground=PAGEFG, background=PAGEBG)
            style.configure('nb.TRadiobutton', foreground=PAGEFG, background=PAGEBG)
        self.grid(padx=10, pady=10, sticky=tk.NSEW)

class Frame(ttk.Frame):
    """Custom ttk.Frame class to fix some display issues."""
    def __init__(self, master: Any = None, **kw):
        style = 'nb.TFrame' if sys.platform == 'win32' else None
        super().__init__(master, style=style, **kw)  # type: ignore
        ttk.Frame(self).grid(pady=5)
        self.configure(takefocus=1)

class Label(ttk.Label):
    def __init__(self, master: Any = None, **kw):
        fg_color = PAGEFG if sys.platform == 'win32' else (ttk.Style().lookup('TLabel', 'foreground') or '')
        bg_color = PAGEBG if sys.platform == 'win32' else (ttk.Style().lookup('TLabel', 'background') or '')
        kw['foreground'] = kw.pop('foreground', fg_color)
        kw['background'] = kw.pop('background', bg_color)
        super().__init__(master, **kw)

class EntryMenu(ttk.Entry):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ttk.Entry.__init__(self, *args, **kwargs)
        self.menu = tk.Menu(self, tearoff=False)
        self.menu.add_command(label="Copy", command=self.copy)
        self.menu.add_command(label="Cut", command=self.cut)
        self.menu.add_separator()
        self.menu.add_command(label="Paste", command=self.paste)
        self.menu.add_separator()
        self.menu.add_command(label="Select All", command=self.select_all)
        self.bind("<Button-3>", self.display_popup)

    def display_popup(self, event: tk.Event) -> None:
        self.menu.post(event.x_root, event.y_root)

    def select_all(self) -> None:
        self.selection_range(0, tk.END)
        self.focus_set()

    def copy(self) -> None:
        if self.selection_present():
            self.clipboard_clear()
            self.clipboard_append(self.selection_get())

    def cut(self) -> None:
        if self.selection_present():
            self.copy()
            self.delete(tk.SEL_FIRST, tk.SEL_LAST)

    def paste(self) -> None:
        try:
            text = self.clipboard_get()
            if self.selection_present() and text:
                self.delete(tk.SEL_FIRST, tk.SEL_LAST)
            self.insert(tk.INSERT, text)
        except tk.TclError:
            pass

class Button(ttk.Button):
    def __init__(self, master: Any = None, **kw):
        style = 'nb.TButton' if sys.platform == 'win32' else None
        super().__init__(master, style=style, **kw)

class Checkbutton(ttk.Checkbutton):
    def __init__(self, master: Any = None, **kw):
        style = 'nb.TCheckbutton' if sys.platform == 'win32' else None
        super().__init__(master, style=style, **kw)

class Radiobutton(ttk.Radiobutton):
    def __init__(self, master: Any = None, **kw):
        style = 'nb.TRadiobutton' if sys.platform == 'win32' else None
        super().__init__(master, style=style, **kw)

class OptionMenu(ttk.OptionMenu):
    def __init__(self, master: Any, variable: Any, default: Any = None, *values: Any, **kw):
        if sys.platform == 'win32':
            ttk.OptionMenu.__init__(self, master, variable, default, *values, style='nb.TMenubutton', **kw)
            self['menu'].configure(background=PAGEBG)
        else:
            ttk.OptionMenu.__init__(self, master, variable, default, *values, **kw)
            self['menu'].configure(background=ttk.Style().lookup('TMenu', 'background'))
        for i in range(0, self['menu'].index('end') + 1):
            self['menu'].entryconfig(i, variable=variable)

class ScrollableNotebook(ttk.Notebook):
    def __init__(self, master: Any = None, tabmenu: bool = False, on_tab_change: Any = None, **kwargs: Any):
        super().__init__(master, **kwargs)
        self.xLocation = 0
        self.timer: str | None = None
        self.menuSpace = 50 if tabmenu else 30
        self.contentsManaged = []
        self.notebookContent = ttk.Notebook(self, **kwargs)
        self.notebookContent.pack(fill="both", expand=True)
        self.notebookContent.bind("<Configure>", self._reset_slide)
        self.notebookTab = ttk.Notebook(self, **kwargs)
        self.notebookTab.place(x=0, y=0)
        self.notebookTab.bind("<<NotebookTabChanged>>", self._tab_changer)
        if on_tab_change:
            self.notebookTab.bind("<<NotebookTabChanged>>", on_tab_change, add='+')
        slide_frame = ttk.Frame(self)
        slide_frame.place(relx=1.0, x=0, y=1, anchor=tk.NE)
        if tabmenu:
            menu_btn = ttk.Label(slide_frame, text="\u2630")
            menu_btn.bind("<ButtonPress-1>", self._bottom_menu)
            menu_btn.pack(side=tk.RIGHT)
        left_arrow = ttk.Label(slide_frame, text=" \u276e")
        left_arrow.bind("<ButtonPress-1>", self._left_slide_start)
        left_arrow.bind("<ButtonRelease-1>", self._slide_stop)
        left_arrow.pack(side=tk.LEFT)
        right_arrow = ttk.Label(slide_frame, text=" \u276f")
        right_arrow.bind("<ButtonPress-1>", self._right_slide_start)
        right_arrow.bind("<ButtonRelease-1>", self._slide_stop)
        right_arrow.pack(side=tk.RIGHT)
        self.grid(padx=10, pady=10, sticky=tk.NSEW)

    def _bottom_menu(self, event: Any) -> None:
        menu = tk.Menu(self, tearoff=0)
        for tab in self.notebookTab.tabs():
            label = self.notebookTab.tab(tab, option="text")
            menu.add_command(label=label, command=lambda t=tab: self.select(t))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _tab_changer(self, event: Any) -> None:
        try:
            idx = self.notebookTab.index("current")
            self.notebookContent.select(idx)
        except Exception:
            pass

    def _right_slide_start(self, event: Any = None) -> None:
        if self._right_slide(event):
            self.timer = self.after(100, self._right_slide_start)

    def _right_slide(self, event: Any = None) -> bool:
        tabs_w = self.notebookTab.winfo_width()
        content_w = self.notebookContent.winfo_width()
        if tabs_w > content_w - self.menuSpace:
            remaining = content_w - (tabs_w + self.notebookTab.winfo_x())
            if remaining <= self.menuSpace + 5:
                self.xLocation -= 20
                self.notebookTab.place(x=self.xLocation, y=0)
                return True
        return False

    def _left_slide_start(self, event: Any = None) -> None:
        if self._left_slide(event):
            self.timer = self.after(100, self._left_slide_start)

    def _left_slide(self, event: Any = None) -> bool:
        if self.notebookTab.winfo_x() != 0:
            self.xLocation += 20
            self.notebookTab.place(x=self.xLocation, y=0)
            return True
        return False

    def _slide_stop(self, event: Any) -> None:
        if self.timer is not None:
            self.after_cancel(self.timer)
            self.timer = None

    def _reset_slide(self, event: Any = None) -> None:
        self.notebookTab.place(x=0, y=0)
        self.xLocation = 0

    def add(self, child: Any, **kwargs: Any) -> None:
        has_tabs = len(self.notebookTab.tabs()) > 0
        content_kwargs = kwargs.copy()
        content_kwargs["text"] = ""
        if has_tabs:
            content_kwargs["state"] = "hidden"
        else:
            content_kwargs.pop("state", None)
        self.notebookContent.add(child, **content_kwargs)
        self.notebookTab.add(ttk.Frame(self.notebookTab), **kwargs)
        self.contentsManaged.append(child)

    def _content_tab_id(self, tab_id: str) -> str:
        idx = self.notebookTab.tabs().index(tab_id)
        return self.notebookContent.tabs()[idx]

    def forget(self, tab_id: str) -> None:
        idx = self.notebookTab.index(tab_id)
        content_tab = self._content_tab_id(tab_id)
        self.notebookContent.forget(content_tab)
        self.notebookTab.forget(tab_id)
        self.contentsManaged[idx].destroy()
        self.contentsManaged.pop(idx)

    def hide(self, tab_id: str) -> None:
        self.notebookContent.hide(self._content_tab_id(tab_id))
        self.notebookTab.hide(tab_id)

    def identify(self, x: int, y: int) -> str | None:
        return self.notebookTab.identify(x, y)

    def index(self, tab_id: str) -> int:
        return self.notebookTab.index(tab_id)

    def insert(self, pos: int, child: Any, **kwargs: Any) -> None:
        self.notebookContent.insert(pos, child, **kwargs)
        self.notebookTab.insert(pos, ttk.Frame(self.notebookTab), **kwargs)

    def select(self, tab_id: str) -> None:
        self.notebookTab.select(tab_id)

    def tab(self, tab_id: str, option: str | None = None, **kwargs: Any):
        c_kwargs = kwargs.copy()
        c_kwargs["text"] = ""
        self.notebookContent.tab(self._content_tab_id(tab_id), **c_kwargs)
        return self.notebookTab.tab(tab_id, option=option, **kwargs)

    def tabs(self) -> tuple:
        return self.notebookTab.tabs()

    def enable_traversal(self) -> None:
        self.notebookContent.enable_traversal()
        self.notebookTab.enable_traversal()

# Export the classes
Notebook = Notebook
Frame = Frame
Label = Label
EntryMenu = EntryMenu
Button = Button
Checkbutton = Checkbutton
Radiobutton = Radiobutton
OptionMenu = OptionMenu
ScrollableNotebook = ScrollableNotebook

# For backward compatibility
Notebook = Notebook
Frame = Frame
Label = Label
EntryMenu = EntryMenu
Button = Button
Checkbutton = Checkbutton
Radiobutton = Radiobutton
OptionMenu = OptionMenu
ScrollableNotebook = ScrollableNotebook

__all__ = [
    'Notebook', 'Frame', 'Label', 'EntryMenu', 'Button',
    'Checkbutton', 'Radiobutton', 'OptionMenu', 'ScrollableNotebook'
]