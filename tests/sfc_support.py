"""Fabricated public-register HTML with the observed protocol shape, never real facts."""

import json


def source_page(ce="ZZZ001", kind="C", packet=None):
    if packet is None:
        packet = [
            {
                "lcType": kind,
                "regulatedActivity": {
                    "actType": 1,
                    "actDesc": "Fabricated activity",
                    "cactDesc": "虛構活動",
                    "status": "R",
                },
                "effectivePeriodList": [
                    {
                        "effectiveDate": "Apr 1, 2003 12:00:00 AM",
                        "endDate": None,
                        "isAmloLcCatDeem": False,
                    }
                ],
            }
        ]
    return (
        '<html><div class="licensed-person"><p>Corporation</p><p>Corporation:<span>Fixture Corporation</span><span>虛構測試法團</span><span> ('
        + ce
        + ")</span></p></div><script>var licRecordData = "
        + json.dumps(packet)
        + ";</script></html>"
    ).encode()
