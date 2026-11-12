"""WeasyPrint behind one function, plus the macOS library-path fix it needs.

WeasyPrint loads Pango, HarfBuzz and fontconfig through `dlopen` by leaf name
(`libgobject-2.0.0.dylib`). On macOS, dyld searches `DYLD_FALLBACK_LIBRARY_PATH`,
whose default (`/usr/local/lib:/usr/lib`) does not include Homebrew's prefix on
Apple Silicon, so `import weasyprint` fails on an otherwise correct
`brew install pango`. `ctypes.util.find_library` reads that variable when it is
called rather than at process start, so setting it before the first import is
enough, which is why every import of WeasyPrint has to come through here.
"""

import logging
import os
import platform
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import url2pathname

_HOMEBREW_LIB_DIRS = ("/opt/homebrew/lib", "/usr/local/lib")


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderedPdf:
    pdf: bytes
    pages: int
    # How far down its last page the main flow's text goes, over the page's usable
    # height. None when WeasyPrint's layout tree, which is not a public API, did not
    # look as expected.
    fill: float | None


class PdfEngineUnavailable(Exception):
    """WeasyPrint's system libraries (Pango and friends) are not installed."""


class ResourceRefused(ValueError):
    """A document asked for a resource outside its template directory."""


def _prepare_macos_library_path() -> None:
    if platform.system() != "Darwin":
        return
    existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    parts = [part for part in existing.split(":") if part]
    for lib_dir in _HOMEBREW_LIB_DIRS:
        if lib_dir not in parts and Path(lib_dir).is_dir():
            parts.append(lib_dir)
    if parts:
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(parts)


def _weasyprint() -> Any:
    if "weasyprint" not in sys.modules:
        _prepare_macos_library_path()
    try:
        module = import_module("weasyprint")
    except OSError as error:  # depends on the host's libraries
        raise PdfEngineUnavailable(
            "WeasyPrint ne trouve pas ses bibliothèques système (Pango). "
            "Installez-les : `brew install pango` sur macOS, "
            "`apt install libpango-1.0-0 libpangoft2-1.0-0` sur Debian/Ubuntu."
        ) from error
    # Its messages quote what it could not read, which can be the document's content.
    logging.getLogger("weasyprint").propagate = False
    return module


def _local_fetcher(root: Path) -> Any:
    """A fetcher that reads `data:` URIs and files under `root`, and nothing else.

    WeasyPrint's default fetches any URL, and the documents will carry model output: a
    slot holding an image link would make a render send text to that host. Template
    assets still resolve; the network and the rest of the disk do not.
    """
    urls: Any = import_module("weasyprint.urls")  # after `_weasyprint()`: see the module doc
    root = root.resolve()

    class LocalOnlyFetcher(urls.URLFetcher):
        def fetch(self, url: str, headers: Any = None) -> Any:
            parts = urlsplit(url)
            if parts.scheme.lower() == "file":
                path = Path(url2pathname(parts.path)).resolve()
                if parts.netloc not in ("", "localhost") or not path.is_relative_to(root):
                    raise ResourceRefused(f"resource outside the template refused: {url}")
            return urls.URLFetcher.fetch(self, url, headers)

    return LocalOnlyFetcher(allowed_protocols=("data", "file"))


def render_pdf(html: str, css: str, base_url: Path) -> RenderedPdf:
    """One HTML document with one stylesheet, as PDF bytes, a page count and how full
    the last page is, read from the same layout.

    `base_url` is the template's own directory, so that an asset referenced relatively
    resolves inside the template and nowhere else.
    """
    weasyprint = _weasyprint()
    fetcher = _local_fetcher(base_url)
    # Without it, WeasyPrint ignores the stylesheet's `@font-face` rules without a word.
    font_config = import_module("weasyprint.text.fonts").FontConfiguration()
    document = weasyprint.HTML(string=html, base_url=str(base_url), url_fetcher=fetcher)
    stylesheet = weasyprint.CSS(
        string=css, base_url=str(base_url), url_fetcher=fetcher, font_config=font_config
    )
    rendered = document.render(stylesheets=[stylesheet], font_config=font_config)
    try:
        fill = _last_page_fill(rendered)
    except (AttributeError, IndexError, KeyError, TypeError) as error:
        log.warning("page fill not measured: %s", type(error).__name__)
        fill = None
    return RenderedPdf(pdf=rendered.write_pdf(), pages=len(rendered.pages), fill=fill)


def _last_page_fill(rendered: Any) -> float:
    """Where the main flow's text ends on the last page. Content taken out of the flow
    (`position: absolute` or `fixed`, the side panel) does not count, list markers
    belong to their item, and the page's margin boxes are not content."""
    boxes = import_module("weasyprint.formatting_structure.boxes")

    def bottom(box: Any, out_of_flow: bool) -> float:
        if isinstance(box, boxes.MarginBox):
            return 0.0
        tag = getattr(box, "element_tag", "") or ""
        if box.style["position"] in ("absolute", "fixed") and not tag.endswith("::marker"):
            out_of_flow = True
        lowest = 0.0
        if not out_of_flow and isinstance(box, (boxes.TextBox, boxes.ReplacedBox)) and box.height:
            lowest = box.position_y + box.height
        for child in getattr(box, "children", ()):
            lowest = max(lowest, bottom(child, out_of_flow))
        return lowest

    page_box = rendered.pages[-1]._page_box
    top = page_box.content_box_y()
    return max(0.0, (bottom(page_box, False) - top) / page_box.height)


def engine_available() -> bool:
    try:
        _weasyprint()
    except PdfEngineUnavailable:
        return False
    return True
