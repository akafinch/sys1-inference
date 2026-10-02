"""The app will not start without both OpenJev addresses, so no question reaches a service outside the demo."""

import pytest

from app.main import create_app


@pytest.mark.parametrize("value", [None, ""], ids=["unset", "empty"])
@pytest.mark.parametrize("name", ["OPENJEV_URL", "OPENJEV_LAYA_CPU_URL"])
def test_the_app_refuses_to_start_without_an_address(addresses, monkeypatch, name, value):
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=f"{name} is not set"):
        create_app()
