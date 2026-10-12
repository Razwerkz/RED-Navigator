def test_clipboard_missing_tools_never_raises(monkeypatch):
    import shutil
    from red_navigator import clipboard
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert clipboard.copy_text("Sol") is False
