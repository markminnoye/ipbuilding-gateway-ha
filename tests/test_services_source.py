"""Source-level checks for the dim_start / dim_stop services.

Companion 1.7.0 ships the ``ha_ipbuilding_gateway.dim_start`` and
``ha_ipbuilding_gateway.dim_stop`` services that drive the gateway's
``DIM_START`` / ``DIM_STOP`` actions for native hold-to-dim ramping
(see ``docs/superpowers/specs/2026-06-22-dimmer-button-ramp-protocol-design.md``).

This file mirrors the source-only style of ``test_blueprints_source.py``:
it inspects ``services.yaml``, ``strings.json`` and the translations
directly so it runs without a Home Assistant install. Runtime
registration tests live in the HA-dependent test modules and are
skipped if HA is not installed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_COMPONENT = _REPO / "custom_components" / "ha_ipbuilding_gateway"

_SERVICES_YAML = _COMPONENT / "services.yaml"
_STRINGS_JSON = _COMPONENT / "strings.json"
_TRANSLATIONS_DIR = _COMPONENT / "translations"

# Action names dispatched by the service handlers. They must match the
# gateway's ``gateway_api._execute_command`` action vocabulary.
_EXPECTED_ACTIONS = {"dim_start": "DIM_START", "dim_stop": "DIM_STOP"}


def test_services_yaml_declares_both_services() -> None:
    """``services.yaml`` must declare both ``dim_start`` and ``dim_stop``."""
    yaml = pytest.importorskip("yaml")
    text = _SERVICES_YAML.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    for service in _EXPECTED_ACTIONS:
        assert service in parsed, f"services.yaml is missing `{service}`"
        entry = parsed[service]
        assert "name" in entry, f"{service} is missing `name`"
        assert "description" in entry, f"{service} is missing `description`"
        # Each service must declare a top-level ``target:`` (the HA target
        # selector the blueprint drives via ``target: entity_id:``), restricted
        # to the ``light`` domain. It must NOT be a data field under ``fields``
        # — that would not be merged into the service call as an entity target.
        assert "target" in entry, (
            f"{service} must declare a top-level `target:` selector"
        )
        assert "target" not in entry.get("fields", {}), (
            f"{service} must use a top-level `target:`, not a `fields.target` data field"
        )
        entity = entry["target"].get("entity")
        assert isinstance(entity, dict)
        assert entity.get("domain") == "light", (
            f"{service}.target must restrict the selector to the light domain"
        )


def test_services_module_registers_both_services() -> None:
    """``services.py`` must register dim_start and dim_stop on entry setup."""
    src = (_COMPONENT / "services.py").read_text(encoding="utf-8")
    # Service names + the matching gateway action constants must both appear.
    assert '"dim_start"' in src, "services.py must register `dim_start`"
    assert '"dim_stop"' in src, "services.py must register `dim_stop`"
    assert '"DIM_START"' in src, "services.py must dispatch DIM_START"
    assert '"DIM_STOP"' in src, "services.py must dispatch DIM_STOP"
    # Idempotency guard: registering twice would blow up with
    # ``InvalidServiceId`` on reload. The check must use
    # ``has_service``.
    assert "has_service" in src, (
        "services.async_register_services must short-circuit on re-registration"
    )


def test_service_handlers_are_coroutines_not_lambdas() -> None:
    """Guard against the sync-lambda-returns-coroutine bug.

    ``hass.services.async_register`` must be handed real coroutine functions.
    A ``lambda call: handler(...)`` is a sync callable that returns an
    un-awaited coroutine — HA would classify it as a callback/executor job and
    the dim command would never be sent.
    """
    src = (_COMPONENT / "services.py").read_text(encoding="utf-8")
    assert "lambda call:" not in src, (
        "service handlers must not be registered as a sync lambda returning a coroutine"
    )
    assert "async def _dim_start" in src
    assert "async def _dim_stop" in src


def test_init_wires_services_into_setup_and_unload() -> None:
    """``__init__.py`` must call async_register_services / async_unregister_services."""
    src = (_COMPONENT / "__init__.py").read_text(encoding="utf-8")
    assert "async_register_services" in src, (
        "async_setup_entry must register the dim_start/dim_stop services"
    )
    assert "async_unregister_services" in src, (
        "async_unload_entry must remove the dim_start/dim_stop services"
    )


def test_strings_json_includes_service_names() -> None:
    """``strings.json`` must declare both services for the operator UI."""
    parsed = json.loads(_STRINGS_JSON.read_text(encoding="utf-8"))
    services = parsed.get("services")
    assert isinstance(services, dict)
    for service in _EXPECTED_ACTIONS:
        assert service in services, f"strings.json `services` block is missing `{service}`"
        assert "name" in services[service]
        assert "description" in services[service]


@pytest.mark.parametrize("locale", ["en", "nl"])
def test_translations_include_service_names(locale: str) -> None:
    """Each shipped translation must declare both services."""
    path = _TRANSLATIONS_DIR / f"{locale}.json"
    parsed = json.loads(path.read_text(encoding="utf-8"))
    services = parsed.get("services")
    assert isinstance(services, dict), (
        f"translations/{locale}.json is missing the `services` block"
    )
    for service in _EXPECTED_ACTIONS:
        assert service in services, (
            f"translations/{locale}.json `services` block is missing `{service}`"
        )
        # Translations should not just copy the English default — assert at
        # least the ``name`` differs from the strings.json fallback for nl.
        if locale == "nl":
            fallback = json.loads(_STRINGS_JSON.read_text(encoding="utf-8"))
            assert (
                services[service]["name"]
                != fallback["services"][service]["name"]
            ), (
                f"translations/{locale}.json `{service}.name` is identical to "
                "the strings.json default — translation missing"
            )
