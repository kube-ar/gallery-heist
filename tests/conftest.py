"""Every test runs offline, as in CI, even with a .env that sets up a real model."""

import pytest

from heist import llm as llm_mod


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(llm_mod, "_load_env", lambda: None)
    for k in ("HEIST_LLM_PROVIDER", "HEIST_LLM_MODEL", "HEIST_LLM_EFFORT"):
        monkeypatch.delenv(k, raising=False)
