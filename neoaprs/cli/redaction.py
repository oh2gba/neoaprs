"""What the log and the support bundle show of a setting's value: a secret (a setting with key, secret, password or token in its name) only as `(set, N characters)`, and so are the two settings whose value is
free text that often holds one: `messages/alert_command` is a shell line, where an operator puts the token of a chat service or a push service (`curl https://.../bot123:ABC/sendMessage`), and `update/url` is an
address that may carry a user name and a password. Their default, which every installation has and which holds nothing, is shown as it is."""
from neoaprs.config import DEFAULTS
from neoaprs.configtypes import is_secret, redacted

FREE_TEXT_SECRETS = ("messages/alert_command", "update/url")


def hides(key: str, value: str) -> bool:
    """Is the value one that the log and the bundle do not show?"""
    return is_secret(key) or (key in FREE_TEXT_SECRETS and value != DEFAULTS.to_data()[key])


def shown_value(key: str, value: str) -> str:
    """The value as the log and the support bundle may show it: as it is, or only whether it is set and how long it is (`(set, 14 characters)`, `(empty)`)."""
    if is_secret(key) or not hides(key, value):
        return redacted(key, value)
    return f"(set, {len(value)} characters)" if value else "(empty)"
