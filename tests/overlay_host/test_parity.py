def test_overlay_publishes_and_mirrors():
    from red_navigator.overlay_host import mirror
    text = mirror.to_textual({"event": "FSDJump", "system": "Sol"})
    assert "Sol" in text

def test_port_single_owner(tmp_path):
    from red_navigator.overlay_host import port_owner
    assert port_owner.claim(str(tmp_path), 50123) is True
