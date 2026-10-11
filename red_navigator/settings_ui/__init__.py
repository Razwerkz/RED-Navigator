"""Per-plugin Textual settings UI (Task 5).

:mod:`forms` renders each plugin's ``plugin_prefs`` fields
(bool/text/number/file/dropdown, with readable-text fallback for
unknown tkinter widgets) and applies values through the namespaced
``config_store``; :mod:`host_panel` keeps one panel per loaded plugin
(listed by ``plugin_start3`` name) for the NOVA settings hook.
"""

from . import forms, host_panel

__all__ = ["forms", "host_panel"]
