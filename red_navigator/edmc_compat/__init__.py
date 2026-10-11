"""Clean-room EDMC plugin compatibility layer.

Reimplements the documented EDMC plugin hook contract
(`plugin_start3`, `plugin_stop`, `journal_entry`, `journal_entry_cqc`,
`dashboard_entry`, `cmdr_data` passthrough) without copying EDMC core
source. No tkinter imports: plugin UI is translated by the Textual
settings layer, never embedded.
"""
