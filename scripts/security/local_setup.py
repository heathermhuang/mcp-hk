import json
from pathlib import Path
from mcp_open_data_hk.storage import Store
from mcp_open_data_hk.operations import checkpoint
from mcp_open_data_hk.sources import DISTRICTS

root = Path.cwd()
target = root / ".data/security-local"
target.mkdir(parents=True, exist_ok=True)
store = Store(str(target / "fixture.sqlite3"))
store.publish(
    "restaurants",
    [{"id": "test-licence", "latitude": 22.3, "longitude": 114.1}],
    store.active("restaurants"),
)
store.publish(
    "population",
    [{"id": d["id"] + ":2024", "districtId": d["id"]} for d in DISTRICTS],
    store.active("population"),
)
path, digest = checkpoint(store.path)
(target / "snapshot.tar.gz").write_bytes(path.read_bytes())
path.unlink()
(target / "checksum").write_text(digest)
config = json.loads((root / "deploy/cloudflare/wrangler.jsonc").read_text())
config["name"] = "mcp-hk-security-local"
config.pop("account_id", None)
config.pop("routes", None)
config.pop("triggers", None)
config["workers_dev"] = False
config["main"] = str(target / "fixture-worker.ts")
config["assets"]["directory"] = str(root / "src/mcp_open_data_hk/web")
config["vars"]["PUBLIC_ORIGIN"] = "http://localhost:18787"
config["vars"]["RELEASE_COMMIT"] = "security-local-fixture"
config["containers"][0]["image"] = str(root / "Dockerfile")
config["r2_buckets"][0]["bucket_name"] = "mcp-hk-security-local"
(target / "wrangler.json").write_text(json.dumps(config, indent=2))
(target / ".dev.vars").write_text("OPS_TOKEN=synthetic-local-operations-only\n")
(target / "fixture-worker.ts").write_text(
    """import worker, {McpContainer,AgentAuth,ContainerProxy} from '../../deploy/cloudflare/worker';
import als from '../../tests/fixtures/als.json';
import plate from '../../tests/fixtures/platehk-search.json';
import seehouse from '../../tests/fixtures/seehouse-search.json';
// Synthetic local run: every Worker-originated external fetch is a fixture or denied.
globalThis.fetch = async (input:RequestInfo|URL,init?:RequestInit) => {
 const url=new URL(input instanceof Request?input.url:String(input));
 if(url.hostname==='www.als.gov.hk')return Response.json(als);
 if(url.hostname==='plate.hk')return Response.json(plate);
 if(url.hostname==='see.house')return Response.json(seehouse);
 throw new Error('External fetch denied by isolated security fixture');
};
export {McpContainer,AgentAuth,ContainerProxy};export default worker;
"""
)
