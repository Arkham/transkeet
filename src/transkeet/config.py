import json
import os
import re

CONFIG_DIR = os.path.expanduser("~/.config/transkeet")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.jsonc")

DEFAULT_CONFIG = {
    "hotkey": "cmd_r",
    "model": "mlx-community/parakeet-tdt-0.6b-v3",
}

DEFAULT_CONFIG_JSONC = """\
{
  // Hotkey to hold for push-to-talk recording.
  // Format: modifier+modifier+key  (single key also works)
  // Available modifiers: cmd, shift, ctrl, alt
  // Side-specific variants: cmd_r, cmd_l, shift_r, shift_l, ctrl_r, ctrl_l, alt_r, alt_l
  "hotkey": "cmd_r",

  // Parakeet model identifier (any parakeet-mlx compatible model).
  "model": "mlx-community/parakeet-tdt-0.6b-v3"
}
"""


def _strip_jsonc_comments(text: str) -> str:
    """Remove // and /* */ comments from JSONC text."""
    # Remove single-line comments (but not inside strings)
    result = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != "\\"):
            in_string = not in_string
            result.append(ch)
            i += 1
        elif not in_string and text[i : i + 2] == "//":
            # Skip to end of line
            while i < len(text) and text[i] != "\n":
                i += 1
        elif not in_string and text[i : i + 2] == "/*":
            # Skip to closing */
            i += 2
            while i < len(text) - 1 and text[i : i + 2] != "*/":
                i += 1
            i += 2
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before } or ]."""
    return re.sub(r",\s*([}\]])", r"\1", text)


def ensure_config() -> dict:
    """Load config from disk, creating defaults if needed."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w") as f:
            f.write(DEFAULT_CONFIG_JSONC)
        return dict(DEFAULT_CONFIG)

    with open(CONFIG_PATH) as f:
        raw = f.read()

    stripped = _strip_jsonc_comments(raw)
    stripped = _strip_trailing_commas(stripped)
    try:
        user_cfg = json.loads(stripped)
    except json.JSONDecodeError as e:
        print(f"Warning: failed to parse {CONFIG_PATH}: {e}")
        print("Using default config.")
        return dict(DEFAULT_CONFIG)

    merged = dict(DEFAULT_CONFIG)
    merged.update(user_cfg)
    return merged
