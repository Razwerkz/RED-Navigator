"""
Shim module for EDMC's config module.
Provides the interfaces that EDMC plugins expect.
"""
from __future__ import annotations

import contextlib
import logging
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import tomllib
import tomli_w
from collections import defaultdict
from typing import Any, TypeVar
import semantic_version

# Constants
GITVERSION_FILE = ".gitversion"
appname = "EDMarketConnector"
applongname = "Elite Dangerous Market Connector"
appcmdname = "EDMC"
copyright = "© 2015-2019 Jonathan Harris, 2020-2026 EDCD"
IS_FROZEN = getattr(sys, 'frozen', False)

# Module-level logger
logger = logging.getLogger("EDMarketConnector")

# Module-level config instance (set by get_config())
config: "Config | None" = None

# Version info
_static_appversion = "6.1.2"
_cached_version: semantic_version.Version | None = None

def appversion() -> semantic_version.Version:
    global _cached_version
    if _cached_version is not None:
        return _cached_version
    _cached_version = semantic_version.Version(_static_appversion)
    return _cached_version

def appversion_nobuild() -> semantic_version.Version:
    return appversion()

user_agent: str = f"EDMarketConnector-{appversion()}"

class Config:
    """Platform-unified Config class."""
    
    # Output flags
    OUT_EDDN_SEND_STATION_DATA = 1
    OUT_MKT_TD = 4
    OUT_MKT_CSV = 8
    OUT_SHIP = 16
    OUT_MKT_MANUAL = 1024
    OUT_EDDN_SEND_NON_STATION = 2048
    OUT_EDDN_DELAY = 4096
    OUT_STATION_ANY = OUT_EDDN_SEND_STATION_DATA | OUT_MKT_TD | OUT_MKT_CSV

    app_dir_path: pathlib.Path
    plugin_dir_path: pathlib.Path
    default_plugin_dir_path: pathlib.Path
    internal_plugin_dir_path: pathlib.Path
    respath_path: pathlib.Path
    home_path: pathlib.Path
    default_journal_dir_path: pathlib.Path
    identifier: str

    def __init__(self, app_path: str | pathlib.Path) -> None:
        self.home_path = pathlib.Path.home()
        self.app_dir_path = pathlib.Path(app_path)
        self.toml_path: pathlib.Path = self.app_dir_path / "config.toml"
        self._write_lock = threading.Lock()
        self._dirty = False
        self._batch_depth = 0
        self.generated: str | None = None
        self.source: str | None = None
        self.settings: dict[str, Any] = {}
        self._load()
        self.default_plugin_dir_path = self.app_dir_path / "plugins"
        plugdir_str = self.get_str("plugin_dir")
        if not plugdir_str:
            plugdir_str = str(self.default_plugin_dir_path)
            self.plugin_dir_path = self.default_plugin_dir_path
            self.set("plugin_dir", plugdir_str)
        if not pathlib.Path(plugdir_str).is_dir():
            self.set("plugin_dir", str(self.default_plugin_dir_path))
            plugdir_str = self.default_plugin_dir
        self.plugin_dir_path = pathlib.Path(self.get('plugin_dir'))
        self.plugin_dir_path.mkdir(exist_ok=True)
        self._init_platform()

    def _init_platform(self):
        if sys.platform == "linux":
            self.internal_plugin_dir_path = self.app_dir_path / "plugins"
            self.respath_path = self.app_dir_path
            self.default_journal_dir_path = pathlib.Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
        elif sys.platform == "win32":
            self.internal_plugin_dir_path = self.app_dir_path / "plugins"
            self.respath_path = self.app_dir_path
            self.default_journal_dir_path = pathlib.Path(os.getenv("LOCALAPPDATA", "")) / "Frontier Developments" / "Elite Dangerous"
        else:
            self.internal_plugin_dir_path = self.app_dir_path / "plugins"
            self.respath_path = self.app_dir_path
            self.default_journal_dir_path = pathlib.Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous"

    def _default_data(self) -> dict:
        return {
            "generated": "",
            "source": "",
            "settings": {},
        }

    def _validate_data(self, data: dict) -> dict:
        if not isinstance(data, dict):
            raise ValueError("Config root is not a table")
        settings = data.get("settings", {})
        if not isinstance(settings, dict):
            raise ValueError("Config 'settings' is not a table")
        return {
            "generated": data.get("generated", ""),
            "source": data.get("source", ""),
            "settings": dict(settings),
        }

    def _load(self):
        self.toml_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.toml_path.exists():
            data = self._default_data()
            self._write_atomic(data)
            self._apply_loaded(data)
            return
        try:
            with self.toml_path.open("rb") as f:
                data = tomllib.load(f)
            data = self._validate_data(data)
            self._apply_loaded(data)
            return
        except (tomllib.TOMLDecodeError, OSError, ValueError) as e:
            logger.error(f"Config load failed, attempting recovery: {e!r}")
        data = self._default_data()
        self._write_atomic(data)
        self._apply_loaded(data)

    def _apply_loaded(self, data: dict):
        self.generated = data.get("generated", "")
        self.source = data.get("source", "")
        self.settings = dict(data.get("settings", {}))

    def _write_atomic(self, data: dict):
        with self._write_lock:
            tmp = self.toml_path.with_suffix(".toml.tmp")
            bak = self.toml_path.with_suffix(".toml.bak")
            with tmp.open("wb") as f:
                tomli_w.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
            if self.toml_path.exists():
                with contextlib.suppress(Exception):
                    self.toml_path.replace(bak)
            tmp.replace(self.toml_path)
            with contextlib.suppress(Exception):
                try:
                    with self.toml_path.parent.open("rb") as d:
                        os.fsync(d.fileno())
                except (IsADirectoryError, PermissionError, OSError):
                    pass

    def get(self, key: str, default=None):
        return self.settings.get(key.lower(), default)

    def get_str(self, key: str, default="") -> str:
        val = self.get(key.lower(), None)
        return str(val) if val is not None else default

    def get_int(self, key: str, default=0) -> int:
        val = self.get(key.lower())
        if isinstance(val, int):
            return val
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def get_bool(self, key: str, default=False) -> bool:
        val = self.get(key.lower())
        if isinstance(val, bool):
            return val
        if isinstance(val, int):
            return val != 0
        if isinstance(val, str):
            v = val.strip().lower()
            if v in ("1", "true", "yes", "on"):
                return True
            if v in ("0", "false", "no", "off"):
                return False
        return default

    def get_list(self, key: str, default=None):
        val = self.get(key.lower())
        return val if isinstance(val, list) else (default if default is not None else [])

    @property
    def shutting_down(self) -> bool:
        return getattr(self, '_Config__in_shutdown', False)

    def set_shutdown(self):
        self._Config__in_shutdown = True

    def get(self, key: str, default=None):
        return self.settings.get(key.lower(), default)

    def set(self, key: str, value: Any):
        if not isinstance(value, (str, int, float, bool, list, dict, type(None))):
            raise TypeError(f"Unsupported config value type for {key!r}: {type(value).__name__}")
        key = key.lower().strip()
        with self._write_lock:
            self.settings[key] = value
            self._dirty = True
        if self._batch_depth == 0:
            self.save()

    def begin_batch(self):
        self._batch_depth = getattr(self, '_batch_depth', 0) + 1

    def end_batch(self):
        if getattr(self, '_batch_depth', 0) == 0:
            raise RuntimeError("end_batch() called without matching begin_batch()")
        self._batch_depth -= 1
        if self._batch_depth == 0 and self._dirty:
            self.save()

    def save(self):
        if getattr(self, '_batch_depth', 0) > 0:
            return
        data = {
            "generated": self.generated,
            "source": self.source,
            "settings": self.settings,
        }
        self._write_atomic(data)
        self._dirty = False

    def close(self):
        self.save()

    # Properties for compatibility
    @property
    def app_dir(self) -> str:
        return str(self.app_dir_path)

    @property
    def plugin_dir(self) -> str:
        return str(self.plugin_dir_path)

    @property
    def default_plugin_dir(self) -> str:
        return str(self.default_plugin_dir_path)

    @property
    def internal_plugin_dir(self) -> str:
        return str(self.internal_plugin_dir_path)

    @property
    def respath(self) -> str:
        return str(self.respath_path)

    @property
    def home(self) -> str:
        return str(self.home_path)

    @property
    def default_journal_dir(self) -> str:
        return str(self.default_journal_dir_path)

def get_appdirpath() -> pathlib.Path:
    if sys.platform == "win32":
        base = pathlib.Path(os.getenv("LOCALAPPDATA", ""))
        return base / appname
    xdg_data_home = pathlib.Path(os.getenv("XDG_DATA_HOME", default="~/.local/share")).expanduser()
    return xdg_data_home / appname

# Module-level config instance - auto-initialize
_config_instance: Config | None = None

def get_config(*args, **kwargs) -> Config:
    global _config_instance
    if _config_instance is None:
        app_dir_path = get_appdirpath()
        _config_instance = Config(app_path=app_dir_path)
    return _config_instance

# For backward compatibility - create a module-level config proxy
class _ConfigProxy:
    def __getattr__(self, name):
        return getattr(get_config(), name)

config = _ConfigProxy()

# Export for compatibility
appversion = appversion
appversion_nobuild = appversion_nobuild
get_update_feed = lambda: "https://raw.githubusercontent.com/EDCD/EDMarketConnector/releases/edmarketconnector.xml"