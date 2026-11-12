"""How a proposal sits on its page, measured on a real render."""

from dataclasses import dataclass

# How full the page should be: below, it reads as half empty.
MIN_FILL = 0.8


@dataclass(frozen=True)
class PageMeasure:
    """A proposal rendered as the draft will first show it."""

    pages: int
    # Elements cut off the bottom of the side panel, which adds no page.
    missing_items: int
    # How full the last page is, 0 to 1; None when it could not be measured.
    fill: float | None
    max_pages: int

    @property
    def column_runs_over(self) -> bool:
        """The main column flows onto a page too many."""
        return self.pages > self.max_pages

    @property
    def panel_runs_over(self) -> bool:
        """The side panel is cut at the bottom of its page, which adds no page: the two
        areas fill apart, each with its own content."""
        return self.missing_items > 0

    @property
    def runs_over(self) -> bool:
        return self.column_runs_over or self.panel_runs_over

    @property
    def in_range(self) -> bool:
        return not self.runs_over and self.fill is not None and self.fill >= MIN_FILL
