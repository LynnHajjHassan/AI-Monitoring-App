"""Small, dependency-free reader for the generated .env camera settings.
For local developer tooling only, never used as the deployed API auth backend.
"""
import ast
from pathlib import Path


def read_env(path):
    values = {}
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        if not key or key.strip() != key:
            continue
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(value[0]):
            value = ast.literal_eval(value)
        values[key] = value
    return values
