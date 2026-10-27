"""Redirect receipts must never retain session-bearing or alternate-host URLs."""

import pytest

from mcp_open_data_hk.curated.hkex_daily.inspection import redirect_metadata, SERIAL


@pytest.mark.parametrize(
    "url",
    [
        "https://di.hkex.com.hk/login?session=SECRET",
        "https://user:SECRET@di.hkex.com.hk/di/NSForm3A.aspx",
        "https://other.test/di/NSForm3A.aspx?fn=" + SERIAL,
        "/di/SECRETSESSION/details?token=SECRET",
        "/di/NSForm3A.aspx?fn=" + SERIAL + "&token=SECRET",
        "/di/NSForm3A.aspx?fn=" + SERIAL + "&sid=SECRET",
        "https://di.hkex.com.hk/di/NSForm3A.aspx?fn=" + SERIAL + "#SECRET",
    ],
)
def test_unknown_redirect_values_and_credentials_are_never_retained(url):
    value = redirect_metadata(url)
    assert value["sanitizedLocation"] is None
    assert "SECRET" not in str(value) and "other.test" not in str(value)
    assert value["redirectFollowed"] is False


def test_only_exact_public_legacy_context_may_be_retained():
    url = "/di/NSForm3A.aspx?fn=" + SERIAL + "&sc=00005&lang=EN"
    assert redirect_metadata(url)["sanitizedLocation"] == url
    assert redirect_metadata(None) == {"present": False}


def test_absolute_operator_deadline_restores_prior_signal_state():
    import signal
    from mcp_open_data_hk.curated.deadline import deadline

    previous = signal.getsignal(signal.SIGALRM)
    with pytest.raises(TimeoutError, match="OPERATOR_REQUEST_DEADLINE"):
        with deadline(20):
            signal.raise_signal(signal.SIGALRM)
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
