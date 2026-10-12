"""Linux clipboard copy via the Wayland/X11 tool chain.

Tries ``wl-copy``, then ``xclip``, then ``xsel``. Returns False when no
tool works. Never raises — minimal systems without clipboard tools are
a silent no-op with a debug log.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

_log = logging.getLogger("red_navigator.clipboard")

_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("wl-copy",),
    ("xclip", "-selection", "clipboard"),
    ("xsel", "--clipboard", "--input"),
)


def copy_text(text: str) -> bool:
    """Copy ``text`` to the system clipboard.

    Returns True on the first tool that accepts the text, False when no
    tool is available or every attempt fails. Never raises.
    """
    try:
        if not isinstance(text, str) or not text:
            return False
        data = text.encode("utf-8")
        for command in _COMMANDS:
            try:
                if shutil.which(command[0]) is None:
                    continue
                subprocess.run(
                    list(command),
                    input=data,
                    timeout=5,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                _log.debug("clipboard tool %r failed", command[0], exc_info=True)
                continue
            return True
        _log.debug("no working clipboard tool found")
        return False
    except Exception:
        _log.debug("copy_text failed", exc_info=True)
        return False
