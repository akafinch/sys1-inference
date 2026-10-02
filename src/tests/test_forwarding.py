"""The app forwards each question to the right OpenJev as one read, and passes the reply back unaltered."""

import json
import os

import httpx
import pytest

BODY = {
    "state": "Every page of our dashboard has returned a 502 error since 8am.",
    "questions": {"broken": {"type": "noul", "instructions": "The product is not working as expected."}},
}


@pytest.mark.parametrize(
    ("target", "address_from", "model"),
    [
        ("diffusiongemma", "OPENJEV_URL", "openjev-0.1"),
        ("laya-gpu", "OPENJEV_URL", "laya-1.0"),
        ("laya-cpu", "OPENJEV_LAYA_CPU_URL", "laya-1.0"),
    ],
)
def test_a_question_goes_to_its_targets_address_and_model_as_one_read(client, openjev, target, address_from, model):
    # An edited body that names another model, or asks for more reads, still goes out as the target's one read.
    r = client.post("/api/ask", json={"target": target, "body": {**BODY, "model": "jev-latest", "samples": 4}})

    [request] = openjev.seen
    assert str(request.url) == os.environ[address_from] + "/v1/systemone"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {**BODY, "model": model, "samples": 1}

    reply = r.json()
    assert r.status_code == 200
    assert reply["openjev"] == openjev.answered
    assert reply["sent"] == json.loads(request.content)
    assert reply["openjev_ms"] == openjev.total_ms
    assert reply["backend_ms"] >= reply["openjev_ms"]


# OpenJev 0.5.1's refusals, verbatim
REFUSALS = {
    400: ({"detail": "Too many score levels. Must have at most 10 levels."}, {}),
    422: (
        {
            "detail": [
                {
                    "type": "missing",
                    "loc": ["body", "questions", "a", "choice", "criteria"],
                    "msg": "Field required",
                    "input": {"type": "choice", "instructions": "Which?"},
                }
            ]
        },
        {},
    ),
    529: ({"detail": {"error_type": "overloaded_error", "message": "OpenJev is at capacity. Retry shortly."}}, {"retry-after": "1"}),
    503: (
        {"detail": {"error_type": "api_error", "message": "inference backend unavailable: ConnectError"}},
        {"retry-after": "2"},
    ),
}


@pytest.mark.parametrize("status", REFUSALS)
def test_a_refusal_keeps_its_status_and_reason(client, openjev, status):
    body, headers = REFUSALS[status]
    openjev.reply = (status, body, headers)

    r = client.post("/api/ask", json={"target": "laya-gpu", "body": BODY})

    assert r.status_code == status
    assert r.json()["openjev"] == body
    assert "answers" not in r.json()["openjev"]


@pytest.mark.parametrize(
    "failure",
    [httpx.ReadTimeout("timed out"), httpx.RemoteProtocolError("Server disconnected")],
    ids=lambda failure: type(failure).__name__,
)
def test_a_transport_failure_is_the_apps_own_502(client, openjev, failure):
    openjev.fail = failure

    r = client.post("/api/ask", json={"target": "diffusiongemma", "body": BODY})

    assert r.status_code == 502
    assert r.json()["openjev"] is None
    assert r.json()["error"] == f"{type(failure).__name__}: {failure}"


def test_an_unreachable_address_is_the_apps_own_502(addresses, monkeypatch, start, openjev):
    monkeypatch.setenv("OPENJEV_LAYA_CPU_URL", "http://nothing-listens.test:8080")
    with start() as client:
        r = client.post("/api/ask", json={"target": "laya-cpu", "body": BODY})
        status = client.get("/api/status").json()

    assert r.status_code == 502
    assert r.json()["openjev"] is None
    assert r.json()["error"] == "ConnectError: [Errno 111] Connection refused"
    assert r.json()["sent"] == {**BODY, "model": "laya-1.0", "samples": 1}
    assert status[1] == {
        "address": "http://nothing-listens.test:8080",
        "device": "cpu",
        "error": "ConnectError: [Errno 111] Connection refused",
    }


def test_a_refusal_without_server_timing_has_no_openjev_time(client, openjev):
    body = {"detail": {"error_type": "api_usage_error", "message": "request body is larger than 67108864 bytes"}}
    openjev.reply = (413, body, {})

    r = client.post("/api/ask", json={"target": "laya-cpu", "body": BODY})

    assert r.status_code == 413
    assert r.json()["openjev"] == body
    assert r.json()["openjev_ms"] is None
    assert r.json()["backend_ms"] >= 0


def test_an_unknown_target_is_refused_before_openjev(client, openjev):
    r = client.post("/api/ask", json={"target": "gpt-5", "body": BODY})

    assert r.status_code == 400
    assert "gpt-5" in r.json()["detail"]
    assert openjev.seen == []


def test_status_lists_the_catalogues_models_by_device(client, addresses):
    assert client.get("/api/status").json() == [
        {"address": addresses["OPENJEV_URL"], "device": "gpu", "models": ["openjev-0.1", "laya-1.0"]},
        {"address": addresses["OPENJEV_LAYA_CPU_URL"], "device": "cpu", "models": ["laya-1.0"]},
    ]
