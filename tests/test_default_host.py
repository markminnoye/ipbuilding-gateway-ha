"""Regression test: manual config flow defaults ``CONF_HOST`` to 127.0.0.1.

Background: a fresh Supervisor add-on install used to leave the
``Host`` field blank in the manual fallback. Operators typing in
``127.0.0.1`` by hand works, but the empty placeholder gave no hint
that the add-on contract is loopback. v0.4.2 makes 127.0.0.1 the
pre-filled default; a standalone install can still override.

Why we don't import ``config_flow``: that module declares a
``ConfigFlow`` subclass and pulls in HA's runtime machinery, which is
out of scope for a pure-Python test. Instead we (1) verify the
default value in ``const.py`` and (2) confirm that ``config_flow.py``
actually *uses* that constant when building the schema. That catches
the realistic regression: someone removes the ``default=`` from the
schema, or hard-codes a string instead of referring to the constant.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

# Minimal ``homeassistant.const`` stub for the companion's ``const`` import.
if "homeassistant" not in sys.modules:
    sys.modules["homeassistant"] = types.ModuleType("homeassistant")
    _const_stub = types.ModuleType("homeassistant.const")
    _const_stub.CONF_HOST = "host"
    _const_stub.CONF_PORT = "port"
    sys.modules["homeassistant.const"] = _const_stub

_REPO = Path(__file__).resolve().parents[1]
_COMP_DIR = _REPO / "custom_components" / "ha_ipbuilding_gateway"

# Synthetic package so ``from .const import`` resolves.
_fake_pkg = types.ModuleType("ha_ipbuilding_gateway")
_fake_pkg.__path__ = [str(_COMP_DIR)]
sys.modules["ha_ipbuilding_gateway"] = _fake_pkg


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"ha_ipbuilding_gateway.{name}", _COMP_DIR / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


const_mod = _load("const")
_config_flow_path = _COMP_DIR / "config_flow.py"


def test_default_api_host_is_loopback() -> None:
    """The canonical Supervisor add-on contract is ``127.0.0.1``."""
    assert const_mod.DEFAULT_API_HOST == "127.0.0.1"


def test_default_api_host_is_a_valid_ipv4() -> None:
    """Defensive: catch typos like ``127.0.0.l1`` or trailing whitespace."""
    import ipaddress

    ip = ipaddress.ip_address(const_mod.DEFAULT_API_HOST)
    assert ip.version == 4


def test_default_api_port_unchanged() -> None:
    """Belt-and-braces: a refactor that touches the host default must not
    silently regress the port default. Catches accidental edits to
    ``DEFAULT_API_PORT`` that would invalidate existing config entries."""
    assert const_mod.DEFAULT_API_PORT == 8080


def test_config_flow_uses_default_api_host_in_schema() -> None:
    """``STEP_USER_DATA_SCHEMA`` must reference ``DEFAULT_API_HOST``.

    We accept either of two binding patterns:

    1. ``vol.Required(CONF_HOST, default=DEFAULT_API_HOST): str``
    2. ``vol.Required("host", default="127.0.0.1"): str`` (hard-coded)

    Pattern 1 is the canonical one and the regression we want to
    catch is "someone removed the default" or "someone hard-coded a
    different value". The grep is intentionally loose so a future
    refactor (e.g. renaming the constant) does not need a test
    update, but it MUST find ``DEFAULT_API_HOST`` near the schema.
    """
    text = _config_flow_path.read_text(encoding="utf-8")

    # 1. The constant must be imported.
    assert "DEFAULT_API_HOST" in text, (
        "config_flow.py no longer references DEFAULT_API_HOST — "
        "did you remove the import?"
    )

    # 2. There must be a ``Required(CONF_HOST, default=...)`` in the
    #    schema block. We look for the substring rather than parse
    #    Python so the test does not depend on voluptuous.
    pattern = re.compile(
        r"vol\.Required\(\s*CONF_HOST\s*,\s*default\s*=\s*DEFAULT_API_HOST\s*\)",
        re.DOTALL,
    )
    assert pattern.search(text), (
        "STEP_USER_DATA_SCHEMA does not pre-fill CONF_HOST with "
        "DEFAULT_API_HOST. Restore the default so manual installs "
        "forget the loopback hint."
    )


def test_strings_describe_loopback_default() -> None:
    """The user-visible description should hint at the add-on default.

    Operators relying solely on the manual flow (no discovery) need to
    know the default is the add-on contract; we surface that hint in
    both English and Dutch so it shows up in the right locale.
    """
    import json

    en = json.loads((_COMP_DIR / "strings.json").read_text(encoding="utf-8"))
    nl = json.loads(
        (_COMP_DIR / "translations" / "nl.json").read_text(encoding="utf-8")
    )

    en_desc = en["config"]["step"]["user"]["description"]
    nl_desc = nl["config"]["step"]["user"]["description"]

    assert "127.0.0.1" in en_desc, "English description lost the loopback hint"
    assert "127.0.0.1" in nl_desc, "Dutch description lost the loopback hint"
