import urllib.request
import urllib.error
import re
import json
from concurrent.futures import ThreadPoolExecutor

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
origin = "http://localhost:18787"


def form(path, data, cookie="", operator=False):
    from urllib.parse import urlencode

    raw = json.dumps(data).encode() if operator else urlencode(data).encode()
    req = urllib.request.Request(
        origin + path,
        data=raw,
        headers={
            "Content-Type": (
                "application/json" if operator else "application/x-www-form-urlencoded"
            ),
            "Origin": origin,
            **({"Cookie": cookie} if cookie else {}),
            **(
                {"Authorization": "Bearer synthetic-local-operations-only"}
                if operator
                else {}
            ),
        },
    )
    try:
        with opener.open(req, timeout=10) as r:
            return r.status, r.headers, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode()


def owner():
    status, h, html = form("/agent/account", {"action": "create"})
    assert status == 200
    return {
        "cookie": h["Set-Cookie"].split(";")[0],
        "csrf": re.search('name="csrf" value="([^"]+)', html)[1],
        "key": re.search("<code>(recover_[^<]+)", html)[1],
        "id": re.search("Account ID: <code>([^<]+)", html)[1],
    }


a = owner()
b = owner()
with ThreadPoolExecutor(max_workers=2) as pool:
    race = list(
        pool.map(
            lambda _: form(
                "/agent/account", {"action": "login", "recovery_key": a["key"]}
            ),
            range(2),
        )
    )
assert sorted(r[0] for r in race) == [200, 401]
assert (
    form("/agent/account", {"action": "rotate", "csrf": a["csrf"]}, a["cookie"])[0]
    == 403
)
assert form("/agent/account", {"action": "login", "recovery_key": a["key"]})[0] == 401
winner = next(r for r in race if r[0] == 200)
cookie = winner[1]["Set-Cookie"].split(";")[0]
csrf = re.search('name="csrf" value="([^"]+)', winner[2])[1]
assert form("/agent/account", {"action": "rotate", "csrf": csrf}, cookie)[0] == 200
assert (
    form("/__ops/agent-auth/contain-owner", {"owner": b["id"]}, operator=True)[0] == 200
)
assert form("/agent/account", {"action": "login", "recovery_key": b["key"]})[0] == 401
print(
    json.dumps(
        {
            "test": "local-platform-auth",
            "raceStatuses": sorted(r[0] for r in race),
            "preRotationCookieAction": 403,
            "oldRecoveryKey": 401,
            "winnerRotation": 200,
            "scopedContainment": 200,
            "containedRecoveryKey": 401,
            "result": "pass",
            "credentials": "omitted",
        }
    )
)
