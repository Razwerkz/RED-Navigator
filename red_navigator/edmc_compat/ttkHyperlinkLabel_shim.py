"""
Shim module for EDMC's ttkHyperlinkLabel module.
Provides HyperlinkLabel widget (stub for non-tkinter environment).
"""
from __future__ import annotations
from typing import Any, Callable, Optional

try:
    import tkinter as tk
    from tkinter import ttk
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False

if TKINTER_AVAILABLE:
    import tkinter as tk
    from tkinter import ttk
    
    class HyperlinkLabel(ttk.Label):
        """A label that acts like a hyperlink."""
        
        def __init__(self, master: Any = None, **kwargs: Any):
            self.url = kwargs.pop('url', '')
            self.callback = kwargs.pop('command', None)
            super().__init__(master, **kwargs)
            self.configure(foreground='blue', cursor='hand2')
            self.bind('<Button-1>', self._on_click)
            self.bind('<Enter>', self._on_enter)
            self.bind('<Leave>', self._on_leave)
        
        def _on_click(self, event: Any) -> None:
            import webbrowser
            if self.url:
                webbrowser.open(self.url)
            if self.callback:
                self.callback()
        
        def _on_enter(self, event: Any) -> None:
            self.configure(foreground='darkblue')
        
        def _on_leave(self, event: Any) -> None:
            self.configure(foreground='blue')
else:
    class HyperlinkLabel:
        """Stub for non-tkinter environments."""
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

__all__ = ['HyperlinkLabel']