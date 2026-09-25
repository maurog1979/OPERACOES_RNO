"""Figuras compatíveis com Plotly.js 2.x e versões atuais de Plotly.py."""
import base64
import json

import numpy as np


def _plain_arrays(value):
    if isinstance(value, dict):
        if "bdata" in value and "dtype" in value:
            array = np.frombuffer(base64.b64decode(value["bdata"]), dtype=value["dtype"])
            if value.get("shape"):
                array = array.reshape(tuple(int(n) for n in value["shape"].split(",")))
            return array.tolist()
        return {key: _plain_arrays(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_arrays(item) for item in value]
    return value


def figure_json(figure):
    return _plain_arrays(json.loads(figure.to_json()))
