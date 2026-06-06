# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2025 Open Computer Use Contributors
"""Shared pytest fixtures for backend patch tests.

Provides byte-identical upstream source as test fixtures for
patch-apply / idempotency / fail-loud coverage. v0.9.6 matches the version
the build targets; v0.9.1 / v0.9.2 retain coverage for version-stable anchors.
"""
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MIDDLEWARE_V091 = FIXTURES_DIR / "middleware_v0.9.1.py"
RETRIEVAL_V091 = FIXTURES_DIR / "retrieval_v0.9.1.py"
MIDDLEWARE_V092 = FIXTURES_DIR / "middleware_v0.9.2.py"
RETRIEVAL_V092 = FIXTURES_DIR / "retrieval_v0.9.2.py"
MIDDLEWARE_V096 = FIXTURES_DIR / "middleware_v0.9.6.py"
RETRIEVAL_V096 = FIXTURES_DIR / "retrieval_v0.9.6.py"


def load_middleware_v091() -> str:
    return MIDDLEWARE_V091.read_text(encoding="utf-8")


def load_retrieval_v091() -> str:
    return RETRIEVAL_V091.read_text(encoding="utf-8")


def load_middleware_v092() -> str:
    return MIDDLEWARE_V092.read_text(encoding="utf-8")


def load_retrieval_v092() -> str:
    return RETRIEVAL_V092.read_text(encoding="utf-8")


def load_middleware_v096() -> str:
    return MIDDLEWARE_V096.read_text(encoding="utf-8")


def load_retrieval_v096() -> str:
    return RETRIEVAL_V096.read_text(encoding="utf-8")
