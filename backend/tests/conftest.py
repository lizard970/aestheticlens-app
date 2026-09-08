import httpx

import pytest


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    """Tests must never spend live provider credits, even with local env configured."""
    monkeypatch.setenv("AESTHETICLENS_PROVIDER", "mock")

    def blocked(*args, **kwargs):
        raise AssertionError("Network access is forbidden in offline tests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)
