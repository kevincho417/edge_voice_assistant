# -*- coding: utf-8 -*-
"""Configuration loading and environment overrides."""
from __future__ import print_function

import copy
import json
import os


class ConfigError(Exception):
    pass


def _deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_json(path):
    try:
        with open(path, "r") as handle:
            return json.load(handle)
    except (IOError, ValueError) as exc:
        raise ConfigError("無法讀取設定檔 {}: {}".format(path, exc))


def resolve_path(base_dir, path):
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base_dir, path))


def load_config(path):
    config = load_json(path)
    project_root = os.path.abspath(os.path.join(os.path.dirname(path), os.pardir))

    mode = os.environ.get("EDGE_ASSISTANT_MODE")
    if mode:
        config.setdefault("assistant", {})["mode"] = mode

    storage = config.setdefault("storage", {})
    storage["database"] = resolve_path(project_root, storage.get("database", "data/assistant.db"))
    storage["recordings_dir"] = resolve_path(
        project_root, storage.get("recordings_dir", "data/recordings")
    )

    config["project_root"] = project_root
    config["config_path"] = os.path.abspath(path)
    return config


def public_config(config):
    """Return UI-safe settings without secrets."""
    result = copy.deepcopy(config)
    result.pop("project_root", None)
    result.pop("config_path", None)
    return result
