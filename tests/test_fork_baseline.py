def test_fork_inventory_pins_nova_hooks():
    import pathlib
    inv = pathlib.Path("docs/superpowers/plans/NOVA_FORK_INVENTORY.md").read_text()
    assert "upstream_commit=" in inv
    assert "NOVA_JOURNAL_TAIL_ENTRY=" in inv
    assert "NOVA_STATUS_FEED_ENTRY=" in inv
    assert "NOVA_SETTINGS_HOOK=" in inv
