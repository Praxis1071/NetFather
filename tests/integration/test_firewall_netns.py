from __future__ import annotations
import os, shutil, subprocess, sys, uuid
import pytest
from firewall.backends import NftablesBackend

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux namespace test")

def _run(args, *, input_text=None, check=True):
    return subprocess.run(args, input=input_text, text=True, capture_output=True, check=check)

def test_nftables_policy_applies_to_an_existing_tcp_connection():
    if os.geteuid() != 0 or not shutil.which("ip") or not shutil.which("nft"):
        pytest.skip("root + ip + nft required")
    token = uuid.uuid4().hex[:6]
    a = f"nfa{token}"
    b = f"nfb{token}"
    va = f"va{token}"
    vb = f"vb{token}"
    port = 24000 + int(token[:4], 16) % 20000
    server_script = (
        "import socket,sys,time\n"
        "s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); "
        f"s.bind(('10.203.0.2',{port})); s.listen(1); s.settimeout(8); "
        "c,_=s.accept(); c.settimeout(8); "
        "open('/tmp/netfather-ready','w').close(); "
        "data=[]; "
        "\nwhile len(data)<2:\n"
        "  try: data.append(c.recv(64))\n"
        "  except socket.timeout: break\n"
        "open('/tmp/netfather-received','wb').write(b'|'.join(data)); "
        "c.close(); s.close()"
    )
    try:
        _run(["ip","netns","add",a]); _run(["ip","netns","add",b])
        _run(["ip","link","add",va,"type","veth","peer","name",vb])
        _run(["ip","link","set",va,"netns",a]); _run(["ip","link","set",vb,"netns",b])
        _run(["ip","-n",a,"addr","add","10.203.0.1/24","dev",va])
        _run(["ip","-n",b,"addr","add","10.203.0.2/24","dev",vb])
        for ns,v in ((a,va),(b,vb)):
            _run(["ip","-n",ns,"link","set","lo","up"]); _run(["ip","-n",ns,"link","set",v,"up"])
        server=_run(["ip","netns","exec",b,sys.executable,"-c",server_script],check=False)
        client_script=(
            "import socket,time\n"
            f"s=socket.create_connection(('10.203.0.2',{port}),timeout=2); "
            "s.sendall(b'first'); time.sleep(0.5); "
            "open('/tmp/netfather-client-ready','w').close(); "
            "time.sleep(2); "
            "s.sendall(b'second'); time.sleep(0.5); "
            "s.sendall(b'third'); time.sleep(1); s.close()"
        )
        client=_run(["ip","netns","exec",a,sys.executable,"-c",client_script],check=False)
        rules=NftablesBackend().preview(["10.203.0.2"])
        applied=_run(["ip","netns","exec",a,"nft","-f","-"],input_text=rules,check=False)
        assert applied.returncode == 0, applied.stderr
        assert client.returncode == 0, client.stderr
        assert server.returncode == 0, server.stderr
    finally:
        subprocess.run(["ip","netns","del",a],capture_output=True)
        subprocess.run(["ip","netns","del",b],capture_output=True)


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

        # Recovery must remove only NetFather's blocking state and restore traffic.
        recovery = _run(
            ["ip", "netns", "exec", a, "nft", "-f", "-"],
            input_text="flush set inet netfather blocked4\n",
            check=False,
        )
        assert recovery.returncode == 0, recovery.stderr
        assert _run(["ip","netns","exec",a,"ping","-c","1","-W","1","10.203.0.2"], check=False).returncode == 0
    finally:
        subprocess.run(["ip","netns","del",a], capture_output=True)
        subprocess.run(["ip","netns","del",b], capture_output=True)
