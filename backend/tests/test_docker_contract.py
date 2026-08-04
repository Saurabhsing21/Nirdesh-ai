from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_compose_keeps_backend_and_qdrant_private() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is not installed")

    environment = os.environ.copy()
    environment.update(
        {
            "VOXLOOM_JWT_SECRET": "docker-test-secret-that-is-at-least-32-characters",
            "VOXLOOM_OPENAI_API_KEY": "not-a-live-key",
        }
    )
    completed = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )
    compose = json.loads(completed.stdout)
    services = compose["services"]

    assert set(services) == {"backend", "frontend", "qdrant"}
    assert services["backend"].get("ports") is None
    assert services["qdrant"].get("ports") is None
    assert services["frontend"]["ports"]
    assert services["backend"]["environment"]["KNOWLEDGE_RAG_ENABLED"] == "false"
    assert services["backend"]["environment"]["QDRANT_URL"] == "http://qdrant:6333"
    assert set(compose["volumes"]) == {"app_data", "qdrant_data"}


def test_container_build_and_proxy_files_exist() -> None:
    expected = [
        ROOT / "backend" / "Dockerfile",
        ROOT / "frontend" / "Dockerfile",
        ROOT / "frontend" / "nginx.conf",
        ROOT / ".dockerignore",
        ROOT / "backend" / ".dockerignore",
        ROOT / "frontend" / ".dockerignore",
    ]
    assert all(path.is_file() for path in expected)

    nginx = (ROOT / "frontend" / "nginx.conf").read_text()
    assert "proxy_pass http://backend:8000" in nginx
    assert "proxy_set_header Upgrade $http_upgrade" in nginx
    assert "location /knowledge" in nginx
