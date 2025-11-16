import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")

from app.main import _discover_project_root


def test_discover_project_root_supports_container_layout(tmp_path):
    container_root = tmp_path / "app"
    backend_dir = container_root / "app"
    frontend_dist = container_root / "frontend" / "dist"

    frontend_dist.mkdir(parents=True)
    backend_dir.mkdir(parents=True)

    fake_main = backend_dir / "main.py"
    fake_main.write_text("# fake main module\n")

    discovered_root = _discover_project_root(fake_main)

    assert discovered_root == container_root.resolve()
    assert (discovered_root / "frontend" / "dist").resolve() == frontend_dist.resolve()
