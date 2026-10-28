"""Serialize data safely inside HTML script elements, including closing tags."""
import json


def script_json(value):
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return (text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
