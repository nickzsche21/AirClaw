"""The patcher is the part 2.x got wrong, so it gets the most tests."""

import json

from airclaw import patch as P


def write(tmp_path, text):
    p = tmp_path / "openclaw.json"
    p.write_text(text, encoding="utf-8")
    return p


def test_writes_documented_schema(tmp_path):
    cfg = write(tmp_path, "{}")
    assert P.patch_openclaw(port=4096, config_path=str(cfg))

    data = json.loads(cfg.read_text())
    provider = data["models"]["providers"]["airclaw"]

    # The exact shape OpenClaw documents. 2.x wrote agent.provider/hostname/port,
    # which OpenClaw ignores entirely.
    assert provider["baseUrl"] == "http://127.0.0.1:4096/v1"
    assert provider["api"] == "openai-completions"
    assert provider["models"][0]["id"] == "airclaw"
    assert provider["models"][0]["cost"]["input"] == 0
    assert data["models"]["mode"] == "merge"
    assert data["agents"]["defaults"]["model"]["primary"] == "airclaw/airclaw"
    assert "hostname" not in provider and "provider" not in data.get("agent", {})


def test_preserves_unrelated_config(tmp_path):
    cfg = write(tmp_path, json.dumps({
        "theme": "dark",
        "agents": {"defaults": {"model": {"fallback": "anthropic/claude"}},
                   "custom": {"keep": True}},
        "models": {"providers": {"openai": {"baseUrl": "https://api.openai.com/v1"}}},
    }))
    assert P.patch_openclaw(config_path=str(cfg))

    data = json.loads(cfg.read_text())
    assert data["theme"] == "dark"
    assert data["agents"]["custom"]["keep"] is True
    assert data["models"]["providers"]["openai"]["baseUrl"] == "https://api.openai.com/v1"
    assert data["agents"]["defaults"]["model"]["fallback"] == "anthropic/claude"
    assert "airclaw" in data["models"]["providers"]


def test_no_default_flag_leaves_primary_alone(tmp_path):
    cfg = write(tmp_path, json.dumps({"agents": {"defaults": {"model": {"primary": "x/y"}}}}))
    assert P.patch_openclaw(config_path=str(cfg), set_default=False)
    data = json.loads(cfg.read_text())
    assert data["agents"]["defaults"]["model"]["primary"] == "x/y"
    assert "airclaw" in data["models"]["providers"]


def test_is_idempotent(tmp_path):
    cfg = write(tmp_path, "{}")
    P.patch_openclaw(config_path=str(cfg))
    first = cfg.read_text()
    P.patch_openclaw(config_path=str(cfg))
    assert cfg.read_text() == first


def test_backup_is_written(tmp_path):
    cfg = write(tmp_path, '{"theme":"dark"}')
    P.patch_openclaw(config_path=str(cfg))
    backup = cfg.with_suffix(cfg.suffix + ".airclaw-backup")
    assert json.loads(backup.read_text()) == {"theme": "dark"}


def test_restore_round_trip(tmp_path):
    cfg = write(tmp_path, '{"theme":"dark"}')
    P.patch_openclaw(config_path=str(cfg))
    assert "airclaw" in cfg.read_text()
    assert P.restore(str(cfg))
    assert json.loads(cfg.read_text()) == {"theme": "dark"}


def test_refuses_unparseable_config(tmp_path):
    cfg = write(tmp_path, "{ this is not json at all ")
    assert P.patch_openclaw(config_path=str(cfg)) is False
    # Untouched, and no backup taken of a file we refused to write.
    assert cfg.read_text() == "{ this is not json at all "


def test_tolerates_comments_and_trailing_commas(tmp_path):
    cfg = write(tmp_path, """
    {
      // the model I usually use
      "theme": "dark", /* block comment */
      "agents": { "defaults": {} },
    }
    """)
    assert P.patch_openclaw(config_path=str(cfg))
    data = json.loads(cfg.read_text())
    assert data["theme"] == "dark"
    assert "airclaw" in data["models"]["providers"]


def test_does_not_clobber_wrong_typed_models_key(tmp_path):
    cfg = write(tmp_path, json.dumps({"models": "not-an-object"}))
    assert P.patch_openclaw(config_path=str(cfg)) is False
    assert json.loads(cfg.read_text()) == {"models": "not-an-object"}


def test_missing_config_without_create_fails(tmp_path):
    assert P.patch_openclaw(config_path=str(tmp_path / "nope.json")) is False


def test_create_flag_makes_config(tmp_path):
    target = tmp_path / "made" / "openclaw.json"
    assert P.patch_openclaw(config_path=str(target), create=True)
    assert "airclaw" in json.loads(target.read_text())["models"]["providers"]


def test_strip_jsonc_keeps_urls_intact():
    # "//" inside a string must survive comment stripping.
    src = '{"baseUrl": "http://127.0.0.1:4096/v1"} // trailing'
    assert json.loads(P._strip_jsonc(src))["baseUrl"] == "http://127.0.0.1:4096/v1"


def test_no_home_directory_glob():
    # 2.x walked the entire home dir. Every candidate must be an explicit path.
    for p in P.candidate_paths():
        assert "*" not in str(p)
