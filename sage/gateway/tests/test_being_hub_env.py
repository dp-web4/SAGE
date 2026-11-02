"""being_hub_env.sh writes a being's hub drain file only for a seed that provably IS the published identity, with
values that source back exactly (GPT on #327). A generated dummy Ed25519 pair in a throwaway HOME; no real key."""
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "being_hub_env.sh"


def _world(hub_url="http://hub.example:8770/a b", flip=False, seed=True):
    home, sage = Path(tempfile.mkdtemp(prefix="hubenv-home-")), Path(tempfile.mkdtemp(prefix="hubenv-sage-"))
    key = crypto.Ed25519PrivateKey.generate()
    raw = key.private_bytes_raw()
    pub = key.public_key().public_bytes_raw().hex()
    if flip:
        pub = ("0" if pub[0] != "0" else "1") + pub[1:]
    (sage / "sage/gateway/hub").mkdir(parents=True)
    (sage / "sage/gateway/hub/test-being.lct_publish.json").write_text(json.dumps(
        {"document": {"id": "11111111-2222-3333-4444-555555555555", "public_key": {"key": pub}}}))
    (home / ".config").mkdir()
    (home / ".config" / "hub-mesh.env").write_text(
        f'CHANNEL_CLIENT="$HOME/bin/channel client"\nHUB_URL="{hub_url}"\nMY_LCT=seat\n')
    if seed:
        (home / ".web4/test-being").mkdir(parents=True)
        (home / ".web4/test-being/channel_key.bin").write_bytes(raw)
    env = dict(os.environ, HOME=str(home))
    env.pop("HUB_MESH_ENV", None)
    run = lambda: subprocess.run([str(SCRIPT), "test-being", "--sage", str(sage)],  # noqa: E731
                                 capture_output=True, text=True, env=env)
    return home, run


def test_a_matching_seed_writes_once_and_the_values_source_back_exactly():
    from sage.gateway.being_inbox_drain import _env_from_file
    home, run = _world()
    r = run()
    assert r.returncode == 0, r.stderr
    out = home / ".config" / "hub-mesh-test-being.env"
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    sourced = subprocess.run(["bash", "-c", 'set -a; source "$1"; printf "%s|%s|%s|%s" "$CHANNEL_CLIENT" '
                              '"$HUB_URL" "$MY_LCT" "$MY_KEYPAIR"', "_", str(out)], capture_output=True, text=True).stdout
    assert sourced == (f"{home}/bin/channel client|http://hub.example:8770/a b|11111111-2222-3333-4444-555555555555|"
                       f"{home}/.web4/test-being/channel_key.bin"), "exact values, spaces kept"
    parsed = _env_from_file(str(out))
    assert parsed["HUB_URL"] == "http://hub.example:8770/a b" and parsed["CHANNEL_CLIENT"] == f"{home}/bin/channel client"
    again = run()
    assert again.returncode == 1 and "not overwriting" in again.stderr


def test_a_seed_that_is_not_the_published_identity_writes_nothing():
    home, run = _world(flip=True)
    r = run()
    assert r.returncode == 1 and "does NOT derive the key" in r.stderr
    assert not (home / ".config" / "hub-mesh-test-being.env").exists()


def test_a_value_that_cannot_be_quoted_safely_writes_nothing():
    home, run = _world(hub_url="http://hub.example:8770/it's")
    r = run()
    assert r.returncode == 1 and "quote or newline" in r.stderr
    assert not (home / ".config" / "hub-mesh-test-being.env").exists()


def test_no_seed_is_refused_with_the_next_step():
    _, run = _world(seed=False)
    r = run()
    assert r.returncode == 1 and "no seed" in r.stderr
