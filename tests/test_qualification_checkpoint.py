from copy import deepcopy

from mcp_open_data_hk.curated.qualification_checkpoint import compare


def test_unchanged_blocked_status_is_quiet_and_changed_failures_retain_receipts(
    tmp_path,
):
    values = {
        "sfc": {
            "data": {
                "state": "not_activated",
                "reasonCode": "SFC_POLICY_NOT_ACTIVATED",
                "unresolvedRequests": 0,
            }
        }
    }
    first = compare(tmp_path, values)
    assert not first["acceptancePassed"]
    assert compare(tmp_path, values) is None
    changed = deepcopy(values)
    changed["sfc"]["data"]["unresolvedRequests"] = 1
    second = compare(tmp_path, changed)
    assert second["previousSha256"] == first["sha256"]
    assert len(list(tmp_path.glob("*.json"))) == 3
