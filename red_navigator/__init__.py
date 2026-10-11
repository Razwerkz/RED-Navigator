"""RED Navigator adapter layer.

Clean-room EDMC plugin compatibility shim plus read-only game feeds.

Nothing here copies EDMC (GPL-2.0) core source; the plugin contract is
reimplemented from the documented hook signatures. Game journals and
dashboard files are only ever read, never written.
"""
