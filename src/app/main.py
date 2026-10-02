"""The demo's backend: it serves the page, and forwards each typed question to OpenJev.

Start it with `uvicorn app.main:create_app --factory --app-dir src`.
"""

import asyncio
import json
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.settings import load_targets

CATALOGUE = json.loads((Path(__file__).parent / "presets.json").read_text(encoding="utf-8"))
PAGE = Path(__file__).resolve().parents[1] / "web" / "dist"  # what `npm run build` writes in src/web

# OpenJev reports its own wall clock for each request as
# "server-timing: model;dur=691.9, server;dur=4.3, total;dur=696.2", in milliseconds.
TOTAL_DUR = re.compile(r"\btotal;dur=(\d+(?:\.\d+)?)")


class Ask(BaseModel):
    target: str  # which model answers: a key of the target table
    body: dict[str, Any]  # OpenJev's request body, as the page's editable box holds it


def create_app(transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """uvicorn calls this with no arguments; the tests pass in a stand-in OpenJev."""
    targets = load_targets()  # first, so a missing address stops the app before it serves

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # One client for every call, so connections to OpenJev are reused. httpx's
        # default timeout is 5 s for everything, too short for a model's first read:
        # https://www.python-httpx.org/advanced/timeouts/
        async with httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            app.state.openjev = client
            yield

    app = FastAPI(title="System 1 inference demo", lifespan=lifespan)

    @app.get("/api/presets")
    async def presets() -> dict:
        # The targets go to the page without their addresses: the browser never calls OpenJev.
        table = {name: {"label": t.label, "model": t.model, "device": t.device} for name, t in targets.items()}
        return {"targets": table, **CATALOGUE}

    @app.get("/api/status")
    async def status() -> list[dict]:
        # One row per OpenJev server and device. It is a listing, not a health check:
        # OpenJev lists a model it passes on to another container even while that one is down.
        places: dict[tuple[str, str], set[str]] = {}
        for t in targets.values():
            places.setdefault((t.address, t.device), set()).add(t.model)
        return await asyncio.gather(*(listing(address, device, models) for (address, device), models in places.items()))

    async def listing(address: str, device: str, wanted: set[str]) -> dict:
        row = {"address": address, "device": device}
        try:
            r = await app.state.openjev.get(f"{address}/v1/models")
            if r.status_code != 200:
                return {**row, "error": f"HTTP {r.status_code}"}
            # OpenJev lists {"models": [{"name": ...}]}, not OpenAI's {"data": [{"id": ...}]}
            listed = [m["name"] for m in r.json()["models"]]
        except (httpx.TransportError, ValueError, KeyError, TypeError) as e:
            return {**row, "error": failure(e)}
        return {**row, "models": [name for name in listed if name in wanted]}

    @app.post("/api/ask")
    async def ask(ask: Ask) -> JSONResponse:
        target = targets.get(ask.target)
        if target is None:
            raise HTTPException(400, f"Unknown target {ask.target!r}: use one of {', '.join(targets)}")
        # The target decides the model. samples: 1 asks for exactly one read: left out,
        # OpenJev reads an uncertain DiffusionGemma answer three more times and averages
        # the four (https://github.com/razorback16/openjev, README).
        sent = {**ask.body, "model": target.model, "samples": 1}
        started = time.perf_counter()
        try:
            # json= sends Content-Type: application/json, without which FastAPI, and so
            # OpenJev, will not read a body: https://fastapi.tiangolo.com/advanced/strict-content-type/
            r = await app.state.openjev.post(f"{target.address}/v1/systemone", json=sent)
        except httpx.TransportError as e:
            # OpenJev never answered (refused, unreachable, timed out): the app's own 502.
            reply = {"openjev": None, "error": failure(e), "openjev_ms": None, "backend_ms": since(started), "sent": sent}
            return JSONResponse(reply, status_code=502)
        backend_ms = since(started)
        try:
            body, error = r.json(), None
        except ValueError:
            body, error = None, f"OpenJev's reply is not JSON: {r.text[:200]}"
        timing = TOTAL_DUR.search(r.headers.get("server-timing", ""))
        reply = {
            "openjev": body,  # unaltered, whatever the status: an answer, or OpenJev's reason
            "error": error,
            # OpenJev sends no timing with the refusals it makes before timing starts (401, 403, 413)
            "openjev_ms": float(timing.group(1)) if timing else None,
            "backend_ms": backend_ms,
            "sent": sent,
        }
        return JSONResponse(reply, status_code=r.status_code)

    # Last: Starlette matches routes in order (https://starlette.dev/routing/), so the
    # page's catch-all at / never hides the API above. Not checked at start, so the API
    # runs, and is tested, before the page is built.
    app.mount("/", StaticFiles(directory=PAGE, html=True, check_dir=False), name="page")
    return app


def since(started: float) -> float:
    """Milliseconds since a perf_counter() reading, to OpenJev's precision."""
    return round((time.perf_counter() - started) * 1000, 1)


def failure(e: Exception) -> str:
    return ": ".join(filter(None, [type(e).__name__, str(e)]))
