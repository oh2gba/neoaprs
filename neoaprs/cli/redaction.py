"""What the log and the support bundle show of a setting's value.

A secret is shown only as `(set, N characters)`. So are two free-text settings that may hold
one (`messages/alert_command`, `update/url`), unless they have their default."""
from neoaprs.config import DEFAULTS
from neoaprs.configtypes import is_secret, redacted

FREE_TEXT_SECRETS = ("messages/alert_command", "update/url")


def hides(key: str, value: str) -> bool:
    """Return whether the log and the bundle must not show the value."""
    return is_secret(key) or (key in FREE_TEXT_SECRETS and value != DEFAULTS.to_data()[key])


def shown_value(key: str, value: str) -> str:
    """Return the value as it may be shown: unchanged, or `(set, 14 characters)` / `(empty)`."""
    if is_secret(key) or not hides(key, value):
        return redacted(key, value)
    return f"(set, {len(value)} characters)" if value else "(empty)"
