"""Terminal mirror for Modern Overlay payloads.

Renders the same payload dict the game-window overlay receives over
the broadcaster socket as human-readable terminal text.
"""

from __future__ import annotations

import json


def to_textual(payload: dict) -> str:
    """Render ``payload`` as terminal text.

    The overlay client receives the identical ``payload`` dict over the
    WebSocket/TCP broadcaster; this function formats that same dict
    for a Textual terminal pane. Never raises on odd input.
    """
    if not isinstance(payload, dict):
        return str(payload)
    try:
        event = str(payload.get("event") or "")
        ptype = str(payload.get("type") or "")

        # LegacyOverlay message: the overlay shows ``text`` verbatim.
        if event == "LegacyOverlay" and ptype == "message":
            text = str(payload.get("text") or "")
            pid = str(payload.get("id") or "")
            header = f"[{pid}]" if pid else "[overlay]"
            x = payload.get("x")
            y = payload.get("y")
            loc = f" ({x},{y})" if x is not None and y is not None else ""
            ttl = payload.get("ttl")
            suffix = f" ttl={ttl}" if ttl is not None else ""
            rendered = f"{header} {text}{loc}{suffix}".strip()
            return rendered or text or json.dumps(
                payload, ensure_ascii=False, sort_keys=True, default=str
            )

        # LegacyOverlay shapes / clears.
        if event == "LegacyOverlay":
            pid = str(payload.get("id") or "")
            shape = str(payload.get("shape") or ptype or "")
            text = str(payload.get("text") or "")
            head = f"[{pid}]" if pid else "[overlay]"
            detail = text or f"shape={shape}" if shape else text
            extra_parts = []
            for key in ("color", "x", "y", "ttl", "size"):
                value = payload.get(key)
                if value is not None and value != "":
                    extra_parts.append(f"{key}={value}")
            extra = (" " + " ".join(extra_parts)) if extra_parts else ""
            if detail or extra:
                return f"{head} {detail}{extra}".strip()
            # Fall through to generic rendering below.

        # Journal broadcasts (FSDJump, Location, Docked, ...) and
        # controller/config events: show the fields the overlay keys on.
        parts: list[str] = []
        if event:
            parts.append(event)
        for key in (
            "system",
            "station",
            "cmdr",
            "message",
            "text",
            "label",
            "plugin",
            "profile",
            "action",
        ):
            value = payload.get(key)
            if value is not None and value != "":
                parts.append(f"{key}={value}")
        # Surface common journal aliases without duplicating above.
        for key in ("StarSystem", "StationName", "Commander"):
            value = payload.get(key)
            if value is not None and value != "":
                parts.append(f"{key}={value}")
        if parts:
            # Include any remaining scalar context (e.g. docked flag).
            docked = payload.get("docked")
            if isinstance(docked, bool):
                parts.append(f"docked={docked}")
            return " ".join(str(p) for p in parts)

        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        try:
            return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return str(payload)


def to_lines(payload: dict) -> list[str]:
    """Split :func:`to_textual` output into terminal lines."""
    return to_textual(payload).splitlines() or [""]
