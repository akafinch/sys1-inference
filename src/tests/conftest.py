"""A stand-in OpenJev, so the app is tested without models or a network.

It plugs into the app's HTTP client as an httpx.MockTransport
(https://www.python-httpx.org/advanced/transports/) and answers both addresses the way
OpenJev 0.5.1 does: the same body shapes, the same Server-Timing header.
"""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

ADDRESSES = {
    "OPENJEV_URL": "http://openjev.test:8080",  # DiffusionGemma, and Laya on the GPU
    "OPENJEV_LAYA_CPU_URL": "http://laya-cpu.test:8080",  # Laya on the CPU
}
# What GET /v1/models lists at each: the main server also lists the generation model and an alias.
MODELS = {
    "openjev.test": ["openjev-latest", "openjev-0.1", "diffusiongemma-26b", "laya-1.0"],
    "laya-cpu.test": ["laya-1.0"],
}


class StandIn:
    total_ms = 25.0  # the wall clock it reports for every question

    def __init__(self):
        self.seen: list[httpx.Request] = []  # what it received, in order
        self.answered = None  # the last body it sent back
        self.reply = None  # (status, body, headers) to send instead of an answer
        self.fail = None  # an exception to raise instead of answering

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.url.host not in MODELS:
            raise httpx.ConnectError("[Errno 111] Connection refused", request=request)
        if request.url.path == "/v1/models":
            listed = [{"name": name, "description": "", "release_date": "2026-09-18"} for name in MODELS[request.url.host]]
            return httpx.Response(200, json={"models": listed})
        if self.fail:
            raise self.fail
        status, self.answered, headers = self.reply or (200, self.answer(json.loads(request.content)), {})
        if status in (401, 403, 413):
            # OpenJev refuses these before its clock starts, so they carry no Server-Timing.
            return httpx.Response(status, json=self.answered, headers=headers)
        # Take at least the time it reports, so the app's own measurement can be checked against it.
        await asyncio.sleep(self.total_ms / 1000 + 0.001)
        timing = f"model;dur={self.total_ms - 2:.1f}, server;dur=2.0, total;dur={self.total_ms:.1f}"
        return httpx.Response(status, json=self.answered, headers={"server-timing": timing, **headers})

    @staticmethod
    def answer(asked: dict) -> dict:
        # Laya's answer to a yes/no question, as a real read returned it, for each question asked
        return {
            "model": asked["model"],
            "answers": {qid: {"type": "noul", "noul": 0.1491} for qid in asked["questions"]},
            "usage": {"input_tokens": 192, "output_tokens": 0},
        }


@pytest.fixture
def openjev():
    return StandIn()


@pytest.fixture
def addresses(monkeypatch):
    for name, address in ADDRESSES.items():
        monkeypatch.setenv(name, address)
    return ADDRESSES


@pytest.fixture
def start(openjev):
    """Start the app on the stand-in, with the environment as the test has set it.

    `with` runs the app's lifespan, which opens and closes its HTTP client:
    https://fastapi.tiangolo.com/advanced/testing-events/
    """
    return lambda: TestClient(create_app(transport=httpx.MockTransport(openjev)))


@pytest.fixture
def client(addresses, start):
    with start() as client:
        yield client
