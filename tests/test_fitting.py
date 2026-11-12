"""How a proposal sits on its page."""

from jobingo.domain.fitting import PageMeasure


def test_in_range_is_80_to_100_percent_of_one_page_with_nothing_cut():
    assert PageMeasure(pages=1, missing_items=0, fill=0.85, max_pages=1).in_range
    assert not PageMeasure(pages=1, missing_items=0, fill=0.6, max_pages=1).in_range
    assert not PageMeasure(pages=1, missing_items=1, fill=0.85, max_pages=1).in_range
    assert not PageMeasure(pages=2, missing_items=0, fill=0.1, max_pages=1).in_range
    assert not PageMeasure(pages=1, missing_items=0, fill=None, max_pages=1).in_range


def test_running_over_is_a_page_too_many_or_items_cut_off_the_panel():
    assert PageMeasure(pages=2, missing_items=0, fill=0.1, max_pages=1).runs_over
    assert PageMeasure(pages=1, missing_items=2, fill=0.5, max_pages=1).runs_over
    assert not PageMeasure(pages=1, missing_items=0, fill=0.99, max_pages=1).runs_over
