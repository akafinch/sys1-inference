"""Where each model answers, read from the environment once, at start."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    label: str  # what the page calls it
    address: str  # the base URL of the OpenJev server that answers for it
    model: str  # the model id that server answers to
    device: str  # where the model runs: "gpu" or "cpu"


def load_targets() -> dict[str, Target]:
    """The three models a question can go to, keyed by the name the page sends.

    There is no default address: an unset one stops the app, so a question can only
    ever reach the demo's own models.
    """
    main = _required("OPENJEV_URL")
    laya_cpu = _required("OPENJEV_LAYA_CPU_URL")
    return {
        "diffusiongemma": Target("DiffusionGemma 26B · GPU", main, "openjev-0.1", "gpu"),
        # The main server passes laya-1.0 through to its Laya container on the GPU.
        "laya-gpu": Target("Laya 421M · GPU", main, "laya-1.0", "gpu"),
        # A Laya server answers only to laya-1.0, so the CPU copy is told apart by its
        # address, not its model id.
        "laya-cpu": Target("Laya 421M · CPU", laya_cpu, "laya-1.0", "cpu"),
    }


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set: give it the base URL of an OpenJev server, e.g. http://openjev:8080")
    return value.rstrip("/")
