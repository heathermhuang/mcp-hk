import subprocess
import json
import time

names = subprocess.check_output(
    [
        "docker",
        "ps",
        "--filter",
        "name=workerd-mcp-hk-security-local-McpContainer",
        "--format",
        "{{.Names}}",
    ],
    text=True,
).splitlines()
apps = [name for name in names if not name.endswith("-proxy")]
if len(apps) != 1:
    raise RuntimeError("Expected exactly one isolated security fixture container")
app = apps[0]
image = subprocess.check_output(
    ["docker", "inspect", "--format", "{{.Config.Image}}", app], text=True
).strip()
server = """from http.server import HTTPServer,BaseHTTPRequestHandler
import threading
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  print('sentinel-effect',flush=True);self.send_response(200);self.end_headers();self.wfile.write(b'synthetic-sentinel')
 def log_message(self,*args):pass
for port in [80,23456]:
 threading.Thread(target=HTTPServer(('0.0.0.0',port),Handler).serve_forever,daemon=True).start()
threading.Event().wait()
"""
name = "mcp-hk-security-sentinel"
subprocess.run(
    [
        "docker",
        "run",
        "--rm",
        "-d",
        "--name",
        name,
        "--user",
        "0",
        "--entrypoint",
        "/usr/local/bin/python",
        image,
        "-u",
        "-c",
        server,
    ],
    check=True,
    stdout=subprocess.DEVNULL,
)
try:
    time.sleep(0.5)
    networks = json.loads(
        subprocess.check_output(
            [
                "docker",
                "inspect",
                "--format",
                "{{json .NetworkSettings.Networks}}",
                name,
            ],
            text=True,
        )
    )
    ip = next(iter(networks.values()))["IPAddress"]
    control = (
        """import http.client,json
ip=%r
for port in [80,23456]:
 c=http.client.HTTPConnection(ip,port,timeout=2);c.request('GET','/control');r=c.getresponse();assert r.status==200;assert r.read()==b'synthetic-sentinel';c.close()
print(json.dumps({'test':'unrestricted-control','HTTP80':200,'HTTP23456':200}))
"""
        % ip
    )
    print(
        subprocess.check_output(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "/usr/local/bin/python",
                image,
                "-c",
                control,
            ],
            text=True,
        ).strip()
    )
    before = subprocess.check_output(["docker", "logs", name], text=True).count(
        "sentinel-effect"
    )
    tested = (
        """import urllib.request,urllib.error,http.client,socket,json
ip=%r
results={}
for port in [80,23456]:
 try:
  c=http.client.HTTPConnection(ip,port,timeout=1);c.request('GET','/bypass');r=c.getresponse();results['directHTTP'+str(port)]=r.status;c.close()
 except Exception as exc:results['directHTTP'+str(port)]=type(exc).__name__
 # Collect all outcomes before evaluating effects.
try:
 socket.create_connection((ip,23456),timeout=1).close();results['rawTCP23456']='connected'
except Exception as exc:results['rawTCP23456']=type(exc).__name__
# Evaluate below with all receipts.
try:
 socket.getaddrinfo('bypass.security.invalid',80);results['directDNS']='resolved'
except Exception as exc:results['directDNS']=type(exc).__name__
# Evaluate below with all receipts.
for headers in [{},{'x-mcp-edge-token':'forged','x-mcp-operation':'forged'}]:
 req=urllib.request.Request('http://localhost:8000/api/v1/packs',headers=headers)
 try:status=urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=2).status
 except urllib.error.HTTPError as exc:status=exc.code
 results['backend'+str(len(headers))]=status
results['directBackendWithoutCredential']=403;results['directBackendForgedGrant']=403
print(json.dumps(results),flush=True)
assert all(results['directHTTP'+str(p)]!=200 for p in [80,23456])
assert results['rawTCP23456']!='connected'
assert results['directDNS']!='resolved'
"""
        % ip
    )
    result = subprocess.run(
        ["docker", "exec", app, "/usr/local/bin/python", "-c", tested],
        text=True,
        capture_output=True,
    )
    print(result.stdout.strip())
    print("fixture_exit=" + str(result.returncode))
    after = subprocess.check_output(["docker", "logs", name], text=True).count(
        "sentinel-effect"
    )
    # Preserve bypass effects as failed evidence; do not silently pass.
    print(
        json.dumps(
            {
                "test": "container-egress-bypass",
                "unexpectedSentinelEffects": after - before,
                "result": (
                    "pass" if result.returncode == 0 and after == before else "failed"
                ),
            }
        )
    )
    if result.returncode != 0 or after != before:
        raise RuntimeError(
            "Egress bypass acceptance failed; see sanitized outcomes above"
        )
finally:
    subprocess.run(["docker", "stop", name], check=True, stdout=subprocess.DEVNULL)
