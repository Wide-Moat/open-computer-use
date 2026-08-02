# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Fixture package for backend patch tests.

Fixture files (middleware_v0.11.0.py, retrieval_v0.11.0.py) are
byte-identical extracts from upstream Open WebUI v0.11.0 — DO NOT modify
them. They are not imported as Python modules; they are read as text by the
patch test harness. Their version matches the base the build targets
(openwebui/Dockerfile ARG OPENWEBUI_VERSION); a base bump replaces them.
"""
