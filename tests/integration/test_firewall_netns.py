from __future__ import annotations
import os, shutil, subprocess, sys, uuid
import pytest
from firewall.backends import NftablesBackend

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux namespace test")

def _run(args, *, input_text=None, check=True):
    return subprocess.run(args, input=input_text, text=True, capture_output=True, check=check)

def test_nftables_rules_really_block_isolated_namespace_traffic():
    if os.geteuid() != 0 or not shutil.which("ip") or not shutil.which("nft") or not shutil.which("ping"):
        pytest.skip("root + ip + nft + ping required")
    token = uuid.uuid4().hex[:6]; a=f"nfa{token}"; b=f"nfb{token}"; va=f"va{token}"; vb=f"vb{token}"
    try:
        _run(["ip","netns","add",a]); _run(["ip","netns","add",b])
        _run(["ip","link","add",va,"type","veth","peer","name",vb])
        _run(["ip","link","set",va,"netns",a]); _run(["ip","link","set",vb,"netns",b])
        _run(["ip","-n",a,"addr","add","10.203.0.1/24","dev",va]); _run(["ip","-n",b,"addr","add","10.203.0.2/24","dev",vb])
        for ns,v in ((a,va),(b,vb)):
            _run(["ip","-n",ns,"link","set","lo","up"]); _run(["ip","-n",ns,"link","set",v,"up"])
        assert _run(["ip","netns","exec",a,"ping","-c","1","-W","1","10.203.0.2"], check=False).returncode == 0
        rules=NftablesBackend().preview(["10.203.0.2"])
        applied=_run(["ip","netns","exec",a,"nft","-f","-"], input_text=rules, check=False)
        assert applied.returncode == 0, applied.stderr
        assert _run(["ip","netns","exec",a,"ping","-c","1","-W","1","10.203.0.2"], check=False).returncode != 0
    finally:
        subprocess.run(["ip","netns","del",a], capture_output=True)
        subprocess.run(["ip","netns","del",b], capture_output=True)
