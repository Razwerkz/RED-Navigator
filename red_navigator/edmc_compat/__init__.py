"""
EDMC Compatibility Shim Package.
Installs EDMC module shims into sys.modules for plugin compatibility.
"""
import sys
import logging

logger = logging.getLogger(__name__)

# Import all shim modules
from . import config_shim
from . import myNotebook_shim
from . import theme_shim
from . import l10n_shim
from . import EDMCLogging_shim
from . import edmc_data_shim
from . import companion_shim
from . import plug_shim
from . import monitor_shim
from . import timeout_session_shim
from . import ttkHyperlinkLabel_shim
from . import commodity_shim
from . import shipyard_shim
from . import outfitting_shim
from . import edshipyard_shim

# Install shims into sys.modules
_shim_modules = {
    'config': config_shim,
    'myNotebook': myNotebook_shim,
    'theme': theme_shim,
    'l10n': l10n_shim,
    'EDMCLogging': EDMCLogging_shim,
    'edmc_data': edmc_data_shim,
    'companion': companion_shim,
    'plug': plug_shim,
    'monitor': monitor_shim,
    'timeout_session': timeout_session_shim,
    'ttkHyperlinkLabel': ttkHyperlinkLabel_shim,
    'commodity': commodity_shim,
    'shipyard': shipyard_shim,
    'outfitting': outfitting_shim,
    'edshipyard': edshipyard_shim,
}

def install_shims():
    """Install all EDMC shim modules into sys.modules."""
    for name, module in _shim_modules.items():
        if name not in sys.modules:
            sys.modules[name] = module
            logger.debug(f"Installed EDMC shim: {name}")
        else:
            logger.debug(f"Shim {name} already present in sys.modules")

def uninstall_shims():
    """Remove all EDMC shim modules from sys.modules."""
    for name in _shim_modules:
        if name in sys.modules:
            del sys.modules[name]
            logger.debug(f"Uninstalled EDMC shim: {name}")

# Auto-install on import
install_shims()

# Re-export key symbols for convenience
from .config_shim import config, get_config, Config, appversion, appversion_nobuild
from .edmc_data_shim import (
    FlagsDocked, FlagsLanded, FlagsLandingGearDown, FlagsShieldsUp,
    FlagsSupercruise, FlagsFlightAssistOff, FlagsHardpointsDeployed,
    FlagsInWing, FlagsLightsOn, FlagsCargoScoopDeployed, FlagsSilentRunning,
    FlagsScoopingFuel, FlagsSrvHandbrake, FlagsSrvTurretView,
    FlagsSrvDriveAssist, FlagsFsdMassLocked, FlagsFsdCharging,
    FlagsFsdCooldown, FlagsLowFuel, FlagsOverHeating, FlagsHasLatLong,
    FlagsIsInDanger, FlagsBeingInterdicted, FlagsInMainShip, FlagsInFighter,
    FlagsInSrv, FlagsHudInAnalysisMode, FlagsNightVision,
    FlagsAltitudeFromAverageRadius, FlagsFsDriveDown, FlagsFsdJump,
    Flag2OnFoot, Flag2InTaxi, Flag2InMulticrew,
)

from .companion_shim import CAPIData, SERVER_LIVE, SERVER_LEGACY, SERVER_BETA
from .plug_shim import show_error, show_info, show_warning
from .monitor_shim import game_running, is_live_galaxy
from .timeout_session_shim import TimeoutSession, new_session
from .ttkHyperlinkLabel_shim import HyperlinkLabel

__all__ = [
    'install_shims', 'uninstall_shims',
    'config', 'get_config', 'Config', 'appversion', 'appversion_nobuild',
    'FlagsDocked', 'FlagsLanded', 'FlagsLandingGearDown', 'FlagsShieldsUp',
    'FlagsSupercruise', 'FlagsFlightAssistOff', 'FlagsHardpointsDeployed',
    'FlagsInWing', 'FlagsLightsOn', 'FlagsCargoScoopDeployed', 'FlagsSilentRunning',
    'FlagsScoopingFuel', 'FlagsSrvHandbrake', 'FlagsSrvTurretView',
    'FlagsSrvDriveAssist', 'FlagsFsdMassLocked', 'FlagsFsdCharging',
    'FlagsFsdCooldown', 'FlagsLowFuel', 'FlagsOverHeating', 'FlagsHasLatLong',
    'FlagsIsInDanger', 'FlagsBeingInterdicted', 'FlagsInMainShip', 'FlagsInFighter',
    'FlagsInSrv', 'FlagsHudInAnalysisMode', 'FlagsNightVision',
    'FlagsAltitudeFromAverageRadius', 'FlagsFsDriveDown', 'FlagsFsdJump',
    'Flag2OnFoot', 'Flag2InTaxi', 'Flag2InMulticrew',
    'CAPIData', 'SERVER_LIVE', 'SERVER_LEGACY', 'SERVER_BETA',
    'show_error', 'show_info', 'show_warning',
    'game_running', 'is_live_galaxy',
    'TimeoutSession', 'new_session',
    'HyperlinkLabel',
]