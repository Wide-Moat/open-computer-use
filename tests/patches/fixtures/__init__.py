# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2025 Open Computer Use Contributors
"""Fixture package for backend patch tests.

Fixture files (middleware_v0.9.{1,2,6}.py, retrieval_v0.9.{1,2,6}.py) are
byte-identical extracts from upstream Open WebUI — DO NOT modify them. They
are not imported as Python modules; they are read as text by the patch test
harness. The v0.9.6 fixtures match the version the build targets
(openwebui/Dockerfile ARG OPENWEBUI_VERSION); the v0.9.1 / v0.9.2 fixtures
retain coverage for patches whose anchors are stable across versions.
"""
