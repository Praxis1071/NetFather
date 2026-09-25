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
    ready = f"/tmp/netfather-ready-{token}"
    connected = f"/tmp/netfather-connected-{token}"
    received = f"/tmp/netfather-received-{token}"
    server_script = (
        "import socket,time\n"
        f"s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(('10.203.0.2',{port})); s.listen(1); "
        "s.settimeout(8); c,_=s.accept(); c.settimeout(2); "
        f"open('{ready}','w').close(); "
        "data=[]\n"
        "while True:\n"
        "  try:\n"
        "    chunk=c.recv(64)\n"
        "    if not chunk: break\n"
        "    data.append(chunk)\n"
        "  except socket.timeout: break\n"
        f"open('{received}','wb').write(b'|'.join(data)); c.close(); s.close()"
    )
    client_script = (
        "import socket,time\n"
        f"s=socket.create_connection(('10.203.0.2',{port}),timeout=2); s.sendall(b'first'); "
        f"open('{connected}','w').close(); time.sleep(1.5); "
        "s.sendall(b'second'); time.sleep(1.5); s.sendall(b'third'); time.sleep(0.5); s.close()"
    )
    server = client = None
    try:
        _run(["ip","netns","add",a]); _run(["ip","netns","add",b])
        _run(["ip","link","add",va,"type","veth","peer","name",vb])
        _run(["ip","link","set",va,"netns",a]); _run(["ip","link","set",vb,"netns",b])
        _run(["ip","-n",a,"addr","add","10.203.0.1/24","dev",va])
        _run(["ip","-n",b,"addr","add","10.203.0.2/24","dev",vb])
        for ns,v in ((a,va),(b,vb)):
            _run(["ip","-n",ns,"link","set","lo","up"]); _run(["ip","-n",ns,"link","set",v,"up"])
        server = subprocess.Popen(
            ["ip","netns","exec",b,sys.executable,"-c",server_script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(40):
            if os.path.exists(ready): break
            if server.poll() is not None: break
            import time; time.sleep(0.05)
        assert os.path.exists(ready), "TCP server did not become ready"
        client = subprocess.Popen(
            ["ip","netns","exec",a,sys.executable,"-c",client_script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(40):
            if os.path.exists(connected): break
            if client.poll() is not None: break
            import time; time.sleep(0.05)
        assert os.path.exists(connected), "TCP client did not establish the existing flow"

        rules = NftablesBackend().preview(["10.203.0.2"])
        applied = _run(["ip","netns","exec",a,"nft","-f","-"], input_text=rules, check=False)
        assert applied.returncode == 0, applied.stderr

        import time; time.sleep(0.8)
        recovery = _run(
            ["ip","netns","exec",a,"nft","-f","-"],
            input_text="flush set inet netfather blocked4\n",
            check=False,
        )
        assert recovery.returncode == 0, recovery.stderr

        client_out, client_err = client.communicate(timeout=8)
        server_out, server_err = server.communicate(timeout=8)
        assert client.returncode == 0, client_err
        assert server.returncode == 0, server_err
        data = open(received, "rb").read() if os.path.exists(received) else b""
        assert b"first" in data
        assert b"third" in data
        assert b"second" not in data
    finally:
        if client is not None and client.poll() is None:
            client.kill()
            client.wait()
        if server is not None and server.poll() is None:
            server.kill()
            server.wait()
        for path in (ready, connected, received):
            try: os.unlink(path)
            except FileNotFoundError: pass
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
