def test_import_offers_and_handles_failure(tmp_path):
    from red_navigator.edmc_compat import importer
    assert importer.import_if_empty(str(tmp_path / "red"), str(tmp_path / "missing")) == "failed"


def test_import_copies_when_empty(tmp_path):
    from red_navigator.edmc_compat import importer
    from red_navigator.edmc_compat import config_store
    config_store.clear()
    src = tmp_path / "edmc"
    (src / "plugins" / "demo").mkdir(parents=True)
    (src / "settings.ini").write_text("opt=1\n")
    (src / "plugins" / "demo" / "load.py").write_text("# demo\n")
    dest = tmp_path / "red"
    assert importer.import_if_empty(str(dest), str(src)) == "imported"
    assert (dest / "settings.ini").read_text() == "opt=1\n"
    assert (dest / "plugins" / "demo" / "load.py").read_text() == "# demo\n"
    assert config_store.get_str("import_source", plugin="red_navigator.importer") == str(src)


def test_import_already_present_leaves_dest_alone(tmp_path):
    from red_navigator.edmc_compat import importer
    from red_navigator.edmc_compat import config_store
    config_store.clear()
    dest = tmp_path / "red"
    dest.mkdir()
    (dest / "existing.ini").write_text("keep=1\n")
    src = tmp_path / "edmc"
    src.mkdir()
    (src / "settings.ini").write_text("opt=1\n")
    assert importer.import_if_empty(str(dest), str(src)) == "already-present"
    assert (dest / "existing.ini").read_text() == "keep=1\n"
    assert not (dest / "settings.ini").exists()


def test_import_never_modifies_source(tmp_path):
    from red_navigator.edmc_compat import importer
    from red_navigator.edmc_compat import config_store
    config_store.clear()
    src = tmp_path / "edmc"
    src.mkdir()
    (src / "settings.ini").write_text("opt=1\n")
    before = (src / "settings.ini").read_bytes()
    importer.import_if_empty(str(tmp_path / "red"), str(src))
    assert (src / "settings.ini").read_bytes() == before
    assert sorted(p.name for p in src.iterdir()) == ["settings.ini"]


def test_fresh_setup_prompt_asks_fresh_or_retry():
    from red_navigator.edmc_compat import importer
    prompt = importer.fresh_setup_prompt()
    assert isinstance(prompt, str) and prompt
    lowered = prompt.lower()
    assert "fresh" in lowered and "retry" in lowered
