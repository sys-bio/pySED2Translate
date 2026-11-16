"""A `location` that is an http(s) URL: the generated script reads the model or data file from the URL itself, in
memory, and writes no copy of it.  A local HTTP server stands in for the remote site, so no test needs the network."""
import functools
import http.server
import os
import threading

import pytest

from pysed2translate.runtime import DataError, ops
from pysed2translate.runtime.context import Context
from pysed2translate.runtime.model import SbmlModel

SBML = ("<sbml xmlns='http://www.sbml.org/sbml/level3/version1/core' level='3' version='1'>"
        "<model id='x'><listOfParameters><parameter id='k' value='2' constant='true'/></listOfParameters></model></sbml>")
LANG = "urn:sedml:language:sbml"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def site(tmp_path):
    """Serve tmp_path/site over HTTP; yields (directory, base URL)."""
    root = tmp_path / "site"
    root.mkdir()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_QuietHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield root, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_input_path_leaves_a_url_as_it_is(tmp_path):
    ctx = Context(str(tmp_path), str(tmp_path / "out"), "p")
    for url in ("https://www.ebi.ac.uk/biomodels/model/download/BIOMD0000000012?filename=BIOMD0000000012_url.xml",
                "http://example.org/a/b.csv", "HTTPS://example.org/m.xml"):
        assert ctx.input_path(url) == url
    assert ctx.input_path("m.xml") == os.path.join(str(tmp_path), "m.xml")


def test_a_model_is_read_from_a_url_without_writing_a_file(site, tmp_path):
    root, base = site
    (root / "m.xml").write_text(SBML)
    before = sorted(p for p in tmp_path.rglob("*"))
    model = SbmlModel.load(f"{base}/m.xml", LANG)
    assert model.element_ids() == ["k"]
    assert model.text == SBML
    assert model.source == f"{base}/m.xml"
    assert sorted(p for p in tmp_path.rglob("*")) == before


def test_a_url_that_answers_with_a_web_page_is_refused_by_name(site):
    root, base = site
    (root / "landing.html").write_text("<!doctype html><html><body>a model's web page</body></html>")
    with pytest.raises(DataError, match=r"HTML page.*not a model file"):
        SbmlModel.load(f"{base}/landing.html", LANG)


def test_a_url_that_cannot_be_read_says_why(site):
    _, base = site
    with pytest.raises(DataError, match=r"cannot read the model file at http://127\.0\.0\.1:\d+/missing\.xml: HTTP Error 404"):
        SbmlModel.load(f"{base}/missing.xml", LANG)


def test_csv_data_is_read_from_a_url(site):
    root, base = site
    (root / "d.csv").write_text("t,S1\n0,1\n1,3\n")
    d = ops.csv_import(f"{base}/d.csv", headers=True)
    assert d.values.tolist() == [[0.0, 1.0], [1.0, 3.0]]
    with pytest.raises(DataError, match=r"cannot read the data file at http://127\.0\.0\.1:\d+/none\.csv: HTTP Error 404"):
        ops.csv_import(f"{base}/none.csv")
