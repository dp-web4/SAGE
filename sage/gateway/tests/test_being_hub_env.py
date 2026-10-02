"""being_hub_env.sh writes a being's hub drain env from the seat's settings, the being's published identity and its
own seed: DUMMY values in a throwaway HOME, no real key anywhere (2026-10-02: every admitted being except sprout
and mcnugget skipped its inbox drain, "no being hub env")."""
import json, os, stat, subprocess, tempfile
from pathlib import Path


def test_being_hub_env_writes_once_with_the_published_id_and_refuses_without_a_seed():
    wt = Path(__file__).resolve().parents[3]

    script = wt / "sage/scripts/being_hub_env.sh"
    home = Path(tempfile.mkdtemp(prefix="hubenv-home-"))
    (home / ".config").mkdir()
    (home / ".config" / "hub-mesh.env").write_text('CHANNEL_CLIENT=$HOME/bin/channel_client\nHUB_URL="http://hub.example:8770"\nMY_LCT=seat\n')
    (home / ".web4" / "cbp-being").mkdir(parents=True)
    (home / ".web4" / "cbp-being" / "channel_key.bin").write_bytes(b"dummy")
    env = dict(os.environ, HOME=str(home))
    env.pop("HUB_MESH_ENV", None)

    r = subprocess.run([str(script), "cbp-being"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    out = home / ".config" / "hub-mesh-cbp-being.env"
    body = out.read_text()
    doc = json.load(open(wt / "sage/gateway/hub/cbp-being.lct_publish.json"))
    assert f"MY_LCT={doc['document']['id']}" in body, body
    assert f"CHANNEL_CLIENT={home}/bin/channel_client" in body and "HUB_URL=http://hub.example:8770" in body
    assert f"MY_KEYPAIR={home}/.web4/cbp-being/channel_key.bin" in body
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    r2 = subprocess.run([str(script), "cbp-being"], capture_output=True, text=True, env=env)
    assert r2.returncode == 1 and "not overwriting" in r2.stderr, r2.stderr
    r3 = subprocess.run([str(script), "legion-being"], capture_output=True, text=True, env=env)
    assert r3.returncode == 1 and "no seed" in r3.stderr, r3.stderr

