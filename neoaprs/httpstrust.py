"""The trust of every https request NeoAPRS makes (the update check, Update now, Send logs): the system's root certificates and, beside them, certifi's (Mozilla's list). A fresh Windows fetches a missing root only when a
browser asks for one, so Python, which reads the system's list as it stands, failed with CERTIFICATE_VERIFY_FAILED on GitHub's download servers where the browser of the same computer downloaded the same file (John's
Windows VM, 3 Nov 2026). Adding a list of roots changes no check: the name, the dates and the chain of the server's certificate are verified as before."""
import functools
import logging
import ssl
import urllib.request

log = logging.getLogger("neoaprs.update")


@functools.cache
def https_context() -> ssl.SSLContext:
    """The context of an https request: the system's roots, and certifi's beside them when certifi is there (a copy without it keeps the system's alone)."""
    context = ssl.create_default_context()
    try:
        import certifi
        context.load_verify_locations(cafile=certifi.where())
    except (ImportError, OSError) as e:
        log.info("the https requests trust the system's root certificates only: %s", e)
    return context


def https_handler() -> urllib.request.HTTPSHandler:
    """The handler an opener is built with, so that its https requests use `https_context`."""
    return urllib.request.HTTPSHandler(context=https_context())
