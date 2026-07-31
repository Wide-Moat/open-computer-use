# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Fixture for python-unsafe-yaml-load, consumed by `semgrep test .semgrep/`.
#
# The annotations are the assertion: `ruleid:` marks a line the rule must flag,
# `ok:` a line it must not. `semgrep test` compares them against the rule's own
# output and fails when a line is flagged by a different rule than the one
# named, so a finding raised for the wrong reason does not pass as a finding.
#
# The two unsafe forms live in separate functions on purpose. A rule that only
# reddens on one literal line is a signature, not a rule.

import yaml


def load_manifest_no_loader(text):
    """Form 1: the loader argument is simply absent."""
    # ruleid: python-unsafe-yaml-load
    return yaml.load(text)


def load_manifest_unsafe_entry_point(fh):
    """Form 2: the explicitly unsafe entry point, a different call entirely."""
    # ruleid: python-unsafe-yaml-load
    return yaml.unsafe_load(fh)


def load_manifest_named_unsafe_loader(text):
    """A loader is passed, and it is the unsafe one."""
    # ruleid: python-unsafe-yaml-load
    return yaml.load(text, Loader=yaml.UnsafeLoader)


def load_manifest_full_loader(text):
    """FullLoader is not SafeLoader. Subtraction catches it without naming it."""
    # ruleid: python-unsafe-yaml-load
    return yaml.load(text, Loader=yaml.FullLoader)


def load_frontmatter(text):
    """The form every in-scope call site actually uses. Must stay silent."""
    # ok: python-unsafe-yaml-load
    return yaml.safe_load(text)


def load_with_explicit_safe_loader(text):
    """Equivalent to safe_load, spelled out. Must stay silent."""
    # ok: python-unsafe-yaml-load
    return yaml.load(text, Loader=yaml.SafeLoader)


def load_with_positional_safe_loader(text):
    """Same, passed positionally rather than by keyword. Must stay silent."""
    # ok: python-unsafe-yaml-load
    return yaml.load(text, yaml.SafeLoader)


def dump_is_not_a_load(data):
    """Serialisation is not deserialisation. Must stay silent."""
    # ok: python-unsafe-yaml-load
    return yaml.dump(data)
