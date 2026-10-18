"""Adapter registry. Adding a dataset = one adapter module + one YAML config."""

from __future__ import annotations

import importlib

from scorecard.adapters.base import Adapter, AdapterMeta

_REGISTRY: dict[str, str] = {
    "lendingclub": "scorecard.adapters.lendingclub:LendingClubAdapter",
    "synthetic": "scorecard.adapters.synthetic:SyntheticAdapter",
    "generic": "scorecard.adapters.generic:GenericCSVAdapter",
    "uci": "scorecard.adapters.uci:UCIAdapter",
}


def available_adapters() -> list[str]:
    return sorted(_REGISTRY)


def get_adapter_class(name: str) -> type[Adapter]:
    if name not in _REGISTRY:
        raise KeyError(f"unknown adapter `{name}`; available: {available_adapters()}")
    module_name, class_name = _REGISTRY[name].split(":")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


__all__ = ["Adapter", "AdapterMeta", "available_adapters", "get_adapter_class"]
