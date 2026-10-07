from pathlib import Path


DASHBOARD_INDEX = Path(__file__).resolve().parents[1] / "dashboard" / "index.html"


def test_overview_polls_quickly_only_while_crawling():
    source = DASHBOARD_INDEX.read_text(encoding="utf-8")

    assert "const busy = (stats.running || 0) > 0;" in source
    assert "stats.failed" not in source.split("function scheduleOverviewPoll", 1)[1].split("}", 1)[0]


def test_force_crawl_banner_does_not_cover_topbar():
    source = DASHBOARD_INDEX.read_text(encoding="utf-8")

    assert "position:sticky;top:0" in source
    assert "position:fixed;top:0" not in source
