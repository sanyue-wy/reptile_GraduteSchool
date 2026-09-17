"""Per-domain circuit contracts driven through real HTTP request state machine."""
import socket
from unittest.mock import Mock

import pytest
import requests

from utils.http import BlockedError, MaxRetriesExceeded, PoliteSession, CircuitBreaker


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr("utils.http.time.sleep", lambda seconds: None)
    return PoliteSession(delay_range=(0, 0), max_retries=0, circuit_threshold=2,
                         cooldown_threshold=10, circuit_window=10, timeout=7)


def response(status=200):
    result = requests.Response()
    result.status_code = status
    result.url = "https://one.invalid/list"
    result._content = b"offline"
    return result


def test_initial_state_and_request_timeout_override(session, monkeypatch):
    transport = Mock(return_value=response())
    monkeypatch.setattr(session._session, "request", transport)
    assert not session.is_blocked()
    assert session.get_block_count() == 0
    session.get("https://one.invalid/list", save_raw=False)
    assert transport.call_args.kwargs["timeout"] == 7
    session.get("https://two.invalid/list", timeout=3)
    assert transport.call_args.kwargs["timeout"] == 3
    assert session.stats == {"requests": 2, "success": 2, "failed": 0, "raw_saved": 0}


def test_domain_isolation_block_counts_and_reset(session, monkeypatch):
    transport = Mock(return_value=response(403))
    monkeypatch.setattr(session._session, "request", transport)
    with pytest.raises(MaxRetriesExceeded):
        session.get("https://one.invalid/a")
    assert session.get_block_count("one.invalid") == 1
    with pytest.raises(MaxRetriesExceeded):
        session.get("https://two.invalid/a")
    assert session.get_block_count() == 2
    with pytest.raises(BlockedError):
        session.get("https://one.invalid/b")
    assert session.is_blocked("one.invalid") and not session.is_blocked("two.invalid")
    assert session.tripped_domains == {"one.invalid"}
    snapshot = session.tripped_domains
    snapshot.clear()
    assert session.is_blocked()
    before = transport.call_count
    with pytest.raises(BlockedError):
        session.get("https://one.invalid/never-sent")
    assert transport.call_count == before
    session.clear_cooldown("one.invalid")
    assert session.is_blocked("one.invalid")  # circuit is distinct from cooldown
    assert session.get_block_count("two.invalid") == 1
    session.reset_circuit("one.invalid")
    assert not session.is_blocked("one.invalid")
    transport.return_value = response()
    session.get("https://one.invalid/recovered")
    assert session.get_block_count("two.invalid") == 1


def test_cooldown_reset_does_not_clear_other_domain(monkeypatch):
    session = PoliteSession(delay_range=(0, 0), max_retries=0, cooldown_threshold=1, circuit_threshold=99)
    monkeypatch.setattr(session, "_sleep", lambda: None)
    monkeypatch.setattr(session._session, "request", Mock(return_value=response(429)))
    for domain in ("one.invalid", "two.invalid"):
        with pytest.raises(BlockedError):
            session.get(f"https://{domain}/")
    session.reset_circuit("one.invalid")
    assert session.is_blocked("one.invalid")
    session.clear_cooldown("one.invalid")
    assert not session.is_blocked("one.invalid")
    assert session.is_blocked("two.invalid")
    assert session.get_block_count("two.invalid") == 1


@pytest.mark.parametrize("error", [
    requests.ConnectionError("getaddrinfo failed"),
    requests.ConnectionError(socket.gaierror(-2, "offline DNS")),
])
def test_dns_trips_immediately_without_retry(session, monkeypatch, error):
    session.max_retries = 5
    transport = Mock(side_effect=error)
    monkeypatch.setattr(session._session, "request", transport)
    with pytest.raises(requests.ConnectionError):
        session.get("https://dns.invalid/")
    assert transport.call_count == 1
    assert session.tripped_domains == {"dns.invalid"}
    assert not session.is_blocked("healthy.invalid")
    with pytest.raises(BlockedError):
        session.get("https://dns.invalid/again")
    assert transport.call_count == 1
    assert session.stats["failed"] == 1


def test_failure_causes_and_time_windows_are_independent(session, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("utils.http.time.time", lambda: clock[0])
    transport = Mock()
    monkeypatch.setattr(session._session, "request", transport)
    for exception in (requests.Timeout("late"), requests.ConnectionError("offline")):
        transport.side_effect = exception
        with pytest.raises(type(exception)):
            session.get("https://one.invalid/")
    assert not session.is_blocked("one.invalid")
    clock[0] = 111.0
    transport.side_effect = requests.Timeout("outside prior window")
    with pytest.raises(requests.Timeout):
        session.get("https://one.invalid/")
    assert not session.is_blocked()
    transport.side_effect = None
    transport.return_value = response()
    session.get("https://one.invalid/success")
    clock[0] = 112.0
    transport.side_effect = requests.Timeout("second in window")
    with pytest.raises(requests.Timeout):
        session.get("https://one.invalid/")
    assert session.is_blocked("one.invalid")
    session.reset_circuit("one.invalid")
    with pytest.raises(requests.Timeout):
        session.get("https://one.invalid/")
    assert not session.is_blocked("one.invalid")


def test_http_status_same_cause_trips(session, monkeypatch):
    monkeypatch.setattr(session._session, "request", Mock(return_value=response(500)))
    for _ in range(2):
        with pytest.raises(requests.HTTPError):
            session.get("https://one.invalid/")
    assert session.is_blocked("one.invalid")
    assert session.stats["requests"] == session.stats["failed"] == 2


def test_retry_counts_logical_call_once_and_stops_at_circuit(session, monkeypatch):
    session.max_retries = 5
    transport = Mock(side_effect=requests.Timeout("offline"))
    monkeypatch.setattr(session._session, "request", transport)
    with pytest.raises(requests.Timeout):
        session.get("https://one.invalid/")
    assert transport.call_count == 2
    assert session.stats["requests"] == session.stats["failed"] == 1


def test_compat_adapter_shares_session_state(session):
    adapter = CircuitBreaker(session=session)
    assert not adapter.record("one.invalid", "timeout")
    assert adapter.record("one.invalid", "timeout")
    assert session.is_blocked("one.invalid")
    adapter.reset("one.invalid")
    assert not session.is_blocked()
    adapter.threshold = 1
    assert adapter.threshold == 1
    assert adapter.record("two.invalid", "timeout")
    assert adapter.tripped_domains == session.tripped_domains
