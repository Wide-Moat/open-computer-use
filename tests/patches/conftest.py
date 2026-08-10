# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Shared pytest fixtures for backend patch tests.

Provides byte-identical upstream source as test fixtures for
patch-apply / idempotency / fail-loud coverage. The fixture version tracks
the base the build targets (openwebui/Dockerfile ARG OPENWEBUI_VERSION).
Patch anchors match exactly one upstream shape, so only that version is kept.
"""
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MIDDLEWARE_V0110 = FIXTURES_DIR / "middleware_v0.11.0.py"
RETRIEVAL_V0110 = FIXTURES_DIR / "retrieval_v0.11.0.py"


def load_middleware_v0110() -> str:
    return MIDDLEWARE_V0110.read_text(encoding="utf-8")


def load_retrieval_v0110() -> str:
    return RETRIEVAL_V0110.read_text(encoding="utf-8")
