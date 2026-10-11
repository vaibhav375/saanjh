"""The page's inline script must parse; a stray comment once took the whole app down."""
import shutil
import subprocess

import pytest

PAGE = "site/index.html"


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_inline_script_parses(tmp_path):
    s = open(PAGE, encoding="utf-8").read()
    js = s[s.index('<script>\n"use strict"') + len("<script>"):s.rindex("</script>")]
    f = tmp_path / "app.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_page_has_the_views():
    s = open(PAGE, encoding="utf-8").read()
    for el in ('id="map"', 'id="t-towns"', 'id="t-fires"', 'id="t-teams"', 'id="horizon"', 'id="sheet"', 'id="t-dist"', 'id="open-ev"', 'id="tour"', "maplibre-gl@5.6.0"):
        assert el in s
