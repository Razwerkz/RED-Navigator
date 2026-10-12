"""
Shim module for EDMC's edmc_data module.
Provides constants and static data used by plugins.
"""
from __future__ import annotations
from typing import Dict, Any, Tuple

# Flags from Status.json
FlagsDocked = 1
FlagsLanded = 2
FlagsLandingGearDown = 4
FlagsShieldsUp = 8
FlagsSupercruise = 16
FlagsFlightAssistOff = 32
FlagsHardpointsDeployed = 64
FlagsInWing = 128
FlagsLightsOn = 256
FlagsCargoScoopDeployed = 512
FlagsSilentRunning = 1024
FlagsScoopingFuel = 2048
FlagsSrvHandbrake = 4096
FlagsSrvTurretView = 8192
FlagsSrvDriveAssist = 16384
FlagsFsdMassLocked = 32768
FlagsFsdCharging = 65536
FlagsFsdCooldown = 131072
FlagsLowFuel = 262144
FlagsOverHeating = 524288
FlagsHasLatLong = 1048576
FlagsIsInDanger = 2097152
FlagsBeingInterdicted = 4194304
FlagsInMainShip = 8388608
FlagsInFighter = 16777216
FlagsInSrv = 33554432
FlagsHudInAnalysisMode = 67108864
FlagsNightVision = 134217728
FlagsAltitudeFromAverageRadius = 268435456
FlagsFsDriveDown = 536870912
FlagsFsdJump = 1073741824

# Flag2 values
Flag2OnFoot = 1
Flag2InTaxi = 2
Flag2InMulticrew = 4

# Cargo categories
CARGO_CATEGORIES = {
    "Salvage": "Salvage",
    "Minerals": "Minerals",
    "Metals": "Metals",
    "Technology": "Technology",
    "Consumables": "Consumables",
    "Data": "Data",
    "RareGoods": "Rare Goods",
    "Biotech": "Biotech",
    "Chemicals": "Chemicals",
    "Mining": "Mining",
    "Agricultural": "Agricultural",
    "Medicines": "Medicines",
    "Slavery": "Slavery",
    "Waste": "Waste",
    "PersonalEffects": "Personal Effects",
    "LegalDrugs": "Legal Drugs",
    "Firearms": "Firearms",
    "Explosives": "Explosives",
    "Narcotics": "Narcotics",
    "Tobacco": "Tobacco",
    "Alcohol": "Alcohol",
    "Foods": "Foods",
    "Clothing": "Clothing",
    "Weapons": "Weapons",
    "Medicines": "Medicines",
}

# Material categories
MATERIAL_CATEGORIES = {
    "Raw": "Raw",
    "Manufactured": "Manufactured",
    "Encoded": "Encoded",
    "Component": "Component",
    "Data": "Data",
    "Consumable": "Consumable",
    "Item": "Item",
}

# Engineer data (minimal)
ENGINEERS = {
    "Felicity Farseer": {"planet": "Deciat", "specialty": "FSD"},
    "Marco Qwent": {"planet": "Siri", "specialty": "Shields"},
    "Tod 'The Blaster' McQuinn": {"planet": "Wyrd", "specialty": "Weapons"},
    "Professor Palin": {"planet": "Maia", "specialty": "Shields"},
    "Lori Jameson": {"planet": "Shinrarta Dezhra", "specialty": "FSD"},
    "Elvira Martuuk": {"planet": "Khun", "specialty": "Engines"},
    "Hera Tani": {"planet": "HIP 16503", "specialty": "Power Plant"},
    "Zacariah Nemo": {"planet": "Kuk", "specialty": "Hull"},
    "Lei Cheung": {"planet": "Kun", "specialty": "Power Distributor"},
    "Selene Jean": {"planet": "Eol Prou", "specialty": "Sensors"},
    "Broo Tarquin": {"planet": "HIP 21991", "specialty": "Weapons"},
    "The Dweller": {"planet": "Wregoe", "specialty": "Life Support"},
    "Liz Ryder": {"planet": "Wyrd", "specialty": "Missiles"},
    "Ram Tah": {"planet": "Meene", "specialty": "Guardian Tech"},
}

# Powerplay data
POWERS = [
    "Zachary Hudson",
    "Felicia Winters",
    "Jerome Archer",
    "Yuri Grom",
    "Pranav Antal",
    "Denton Patreus",
    "Arissa Lavigny-Duval",
    "Aisling Duval",
    "Li Yong-Rui",
    "Edmund Mahon",
    "Zemina Torval",
]

# Star classes
STAR_CLASSES = ['O', 'B', 'A', 'F', 'G', 'K', 'M', 'L', 'T', 'Y', 'C', 'N', 'S', 'A_Be', 'B_Be', 'A_Be', 'F_Be', 'G_Be', 'K_Be', 'M_Be', 'L_Be', 'T_Be', 'Y_Be', 'Wolf-Rayet', 'C', 'N', 'S', 'Ae', 'Be', 'Ce', 'Ne', 'Oe', 'Fe', 'Ge', 'He', 'Ie', 'Ke', 'Me', 'Oe', 'Te', 'Ye', 'Ae_Be', 'Be_Be', 'Ce_Be', 'De_Be', 'Ee_Be', 'Fe_Be', 'Ge_Be', 'He_Be', 'Ie_Be', 'Je_Be', 'Ke_Be', 'Le_Be', 'Me_Be', 'Ne_Be', 'Oe_Be', 'Pe_Be', 'Qe_Be', 'Re_Be', 'Se_Be', 'Te_Be', 'Ue_Be', 'Ve_Be', 'We_Be', 'Xe_Be', 'Ye_Be', 'Ze_Be']

# Module categories
MODULE_CATEGORIES = {
    "PowerPlant": "Power Plant",
    "PowerDistributor": "Power Distributor",
    "FrameShiftDrive": "Frame Shift Drive",
    "LifeSupport": "Life Support",
    "PowerConverter": "Power Converter",
    "ShieldGenerator": "Shield Generator",
    "FuelTank": "Fuel Tank",
    "Radar": "Radar",
    "ShipScanner": "Ship Scanner",
    "KillWarrantScanner": "Kill Warrant Scanner",
    "DataLinkScanner": "Data Link Scanner",
    "ManifestScanner": "Manifest Scanner",
    "WakeScanner": "Wake Scanner",
    "ShieldCellBank": "Shield Cell Bank",
    "HeatSinkLauncher": "Heat Sink Launcher",
    "ChaffLauncher": "Chaff Launcher",
    "ECM": "ECM",
    "PointDefence": "Point Defence",
    "CargoHatch": "Cargo Hatch",
    "FuelScoop": "Fuel Scoop",
    "FrameShiftDriveInterdictor": "Frame Shift Drive Interdictor",
    "AutoFieldMaintenanceUnit": "Auto Field Maintenance Unit",
    "DockingComputer": "Docking Computer",
    "VehicleHangar": "Vehicle Hangar",
    "DataCollector": "Data Collector",
    "RepairLimpetController": "Repair Limpet Controller",
    "FuelTransferLimpetController": "Fuel Transfer Limpet Controller",
    "HatchBreakerLimpetController": "Hatch Breaker Limpet Controller",
    "CollectorLimpetController": "Collector Limpet Controller",
    "ProspectorLimpetController": "Prospector Limpet Controller",
    "ShieldBooster": "Shield Booster",
    "CargoRack": "Cargo Rack",
    "PlanetaryVehicleHangar": "Planetary Vehicle Hangar",
    "Cabin": "Cabin",
    "GuardianModuleReinforcementPackage": "Guardian Module Reinforcement Package",
    "GuardianHullReinforcementPackage": "Guardian Hull Reinforcement Package",
    "GuardianShieldReinforcementPackage": "Guardian Shield Reinforcement Package",
    "GuardianFSDBooster": "Guardian FSD Booster",
    "GuardianPowerPlant": "Guardian Power Plant",
    "GuardianPowerDistributor": "Guardian Power Distributor",
}

# Commodity categories
COMMODITY_CATEGORIES = {
    "Metals": "Metals",
    "Minerals": "Minerals",
    "Chemicals": "Chemicals",
    "Technology": "Technology",
    "Consumables": "Consumables",
    "Agricultural": "Agricultural",
    "Medicines": "Medicines",
    "Biotech": "Biotech",
    "Data": "Data",
    "RareGoods": "Rare Goods",
    "Slavery": "Slavery",
    "Waste": "Waste",
    "PersonalEffects": "Personal Effects",
    "LegalDrugs": "Legal Drugs",
    "Firearms": "Firearms",
    "Explosives": "Explosives",
    "Narcotics": "Narcotics",
    "Tobacco": "Tobacco",
    "Alcohol": "Alcohol",
    "Foods": "Foods",
    "Clothing": "Clothing",
    "Weapons": "Weapons",
    "Salvage": "Salvage",
}

# Body types
BODY_TYPES = {
    "Star": "Star",
    "Planet": "Planet",
    "Moon": "Moon",
    "Asteroid": "Asteroid",
    "AsteroidCluster": "Asteroid Cluster",
    "Ring": "Ring",
    "Station": "Station",
    "Outpost": "Outpost",
    "FleetCarrier": "Fleet Carrier",
    "Megaship": "Megaship",
    "Settlement": "Settlement",
    "SurfacePort": "Surface Port",
    "PlanetaryOutpost": "Planetary Outpost",
}

# Rank names
COMBAT_RANKS = ["Harmless", "Mostly Harmless", "Novice", "Competent", "Expert", "Master", "Dangerous", "Deadly", "Elite"]
TRADE_RANKS = ["Penniless", "Mostly Penniless", "Trader", "Dealer", "Merchant", "Broker", "Entrepreneur", "Tycoon", "Elite"]
EXPLORATION_RANKS = ["Aimless", "Mostly Aimless", "Scout", "Surveyor", "Explorer", "Pathfinder", "Ranger", "Pioneer", "Elite"]
CQC_RANKS = ["Helpless", "Mostly Helpless", "Amateur", "Semi Professional", "Professional", "Champion", "Hero", "Legend", "Elite"]
SOLDIER_RANKS = ["Defenceless", "Mostly Defenceless", "Recruit", "Cadet", "Soldier", "Gunner", "Warrior", "Gladiator", "Elite"]
EXOBIOLOGIST_RANKS = ["Directionless", "Mostly Directionless", "Compiler", "Collector", "Cataloguer", "Taxonomist", "Ecologist", "Geneticist", "Elite"]
MERCENARY_RANKS = ["Merciless", "Mostly Merciless", "Hired Gun", "Enforcer", "Assassin", "Warlord", "Conqueror", "Tyrant", "Elite"]

# Powerplay ranks
POWERPLAY_RANKS = [0, 10, 50, 150, 500, 1500, 5000, 10000, 15000, 20000, 25000, 30000, 35000, 40000, 45000, 50000, 55000, 60000, 65000, 70000, 75000, 80000, 85000, 90000, 95000, 100000]

# Flags mapping
FLAGS = {
    "Docked": FlagsDocked,
    "Landed": FlagsLanded,
    "LandingGearDown": FlagsLandingGearDown,
    "ShieldsUp": FlagsShieldsUp,
    "Supercruise": FlagsSupercruise,
    "FlightAssistOff": FlagsFlightAssistOff,
    "HardpointsDeployed": FlagsHardpointsDeployed,
    "InWing": FlagsInWing,
    "LightsOn": FlagsLightsOn,
    "CargoScoopDeployed": FlagsCargoScoopDeployed,
    "SilentRunning": FlagsSilentRunning,
    "ScoopingFuel": FlagsScoopingFuel,
    "SrvHandbrake": FlagsSrvHandbrake,
    "SrvTurretView": FlagsSrvTurretView,
    "SrvDriveAssist": FlagsSrvDriveAssist,
    "FsdMassLocked": FlagsFsdMassLocked,
    "FsdCharging": FlagsFsdCharging,
    "FsdCooldown": FlagsFsdCooldown,
    "LowFuel": FlagsLowFuel,
    "OverHeating": FlagsOverHeating,
    "HasLatLong": FlagsHasLatLong,
    "IsInDanger": FlagsIsInDanger,
    "BeingInterdicted": FlagsBeingInterdicted,
    "InMainShip": FlagsInMainShip,
    "InFighter": FlagsInFighter,
    "InSrv": FlagsInSrv,
    "HudInAnalysisMode": FlagsHudInAnalysisMode,
    "NightVision": FlagsNightVision,
    "AltitudeFromAverageRadius": FlagsAltitudeFromAverageRadius,
    "FsDriveDown": FlagsFsDriveDown,
    "FsdJump": FlagsFsdJump,
}

FLAGS2 = {
    "OnFoot": Flag2OnFoot,
    "InTaxi": Flag2InTaxi,
    "InMulticrew": Flag2InMulticrew,
}

# For backward compatibility
FlagsDocked = FlagsDocked
FlagsLanded = FlagsLanded
FlagsLandingGearDown = FlagsLandingGearDown
FlagsShieldsUp = FlagsShieldsUp
FlagsSupercruise = FlagsSupercruise
FlagsFlightAssistOff = FlagsFlightAssistOff
FlagsHardpointsDeployed = FlagsHardpointsDeployed
FlagsInWing = FlagsInWing
FlagsLightsOn = FlagsLightsOn
FlagsCargoScoopDeployed = FlagsCargoScoopDeployed
FlagsSilentRunning = FlagsSilentRunning
FlagsScoopingFuel = FlagsScoopingFuel
FlagsSrvHandbrake = FlagsSrvHandbrake
FlagsSrvTurretView = FlagsSrvTurretView
FlagsSrvDriveAssist = FlagsSrvDriveAssist
FlagsFsdMassLocked = FlagsFsdMassLocked
FlagsFsdCharging = FlagsFsdCharging
FlagsFsdCooldown = FlagsFsdCooldown
FlagsLowFuel = FlagsLowFuel
FlagsOverHeating = FlagsOverHeating
FlagsHasLatLong = FlagsHasLatLong
FlagsIsInDanger = FlagsIsInDanger
FlagsBeingInterdicted = FlagsBeingInterdicted
FlagsInMainShip = FlagsInMainShip
FlagsInFighter = FlagsInFighter
FlagsInSrv = FlagsInSrv
FlagsHudInAnalysisMode = FlagsHudInAnalysisMode
FlagsNightVision = FlagsNightVision
FlagsAltitudeFromAverageRadius = FlagsAltitudeFromAverageRadius
FlagsFsDriveDown = FlagsFsDriveDown
FlagsFsdJump = FlagsFsdJump

Flag2OnFoot = Flag2OnFoot
Flag2InTaxi = Flag2InTaxi
Flag2InMulticrew = Flag2InMulticrew

__all__ = [
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
    'CARGO_CATEGORIES', 'MATERIAL_CATEGORIES', 'ENGINEERS', 'POWERS',
    'STAR_CLASSES', 'MODULE_CATEGORIES', 'COMMODITY_CATEGORIES', 'BODY_TYPES',
    'COMBAT_RANKS', 'TRADE_RANKS', 'EXPLORATION_RANKS', 'CQC_RANKS',
    'SOLDIER_RANKS', 'EXOBIOLOGIST_RANKS', 'MERCENARY_RANKS',
    'POWERPLAY_RANKS', 'FLAGS', 'FLAGS2',
]