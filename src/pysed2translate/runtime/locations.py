"""Reading what a SED2 `location` names: a local file, or an http(s) URL.

A URL is read in memory and no copy of it is written.  It is read exactly as the document gives it: the script does
not rewrite it (for example from a repository's web page about a model to the URL of the model file), and a URL that
answers with a web page is refused with that reason rather than handed on to a parser.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .annotated import DataError

URL_SCHEMES = ("http", "https")
URL_TIMEOUT = 60.0  # seconds to wait for a remote site before giving up
HTML_TYPES = ("text/html", "application/xhtml+xml")


def is_url(location: str) -> bool:
    return urlsplit(location).scheme.lower() in URL_SCHEMES


def read_text(location: str, what: str, encoding: str = "utf-8") -> str:
    """The text of the file at `location` (a path or an http(s) URL); `what` ("model", "data") names it in errors."""
    if not is_url(location):
        try:
            with open(location, "r", encoding=encoding, newline="") as f:
                return f.read()
        except OSError as e:
            raise DataError(f"cannot read the {what} file {location}: {e}") from e
    try:
        with urllib.request.urlopen(location, timeout=URL_TIMEOUT) as response:
            content_type = response.headers.get_content_type()
            data = response.read()
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise DataError(f"cannot read the {what} file at {location}: {e}") from e
    if content_type in HTML_TYPES:
        raise DataError(f"{location} answered with an HTML page ({content_type}), not a {what} file; the location must "
                        f"be the URL of the file itself")
    try:
        return data.decode(encoding)
    except UnicodeDecodeError as e:
        raise DataError(f"cannot read the {what} file at {location}: {e}") from e
