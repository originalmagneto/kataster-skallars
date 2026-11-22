"""Keep in-process test traffic and quota state isolated per test."""
import pytest

from kataster_mcp import server


@pytest.fixture(autouse=True)
def isolated_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "default_limits_dir", lambda: tmp_path / "limits")


@pytest.fixture
def isolated_subprocess_limits(tmp_path, monkeypatch):
    """Give child interpreters a temporary account home without a production override."""
    import os

    hooks = tmp_path / "python-hooks"
    hooks.mkdir()
    (hooks / "sitecustomize.py").write_text(
        "from pathlib import Path\n"
        "from kataster_mcp import cache\n"
        f"cache._home = lambda: Path({str(tmp_path / 'account')!r})\n",
        encoding="utf-8",
    )
    path = [str(hooks), *filter(None, os.environ.get("PYTHONPATH", "").split(os.pathsep))]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(path))
