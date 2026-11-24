"""Browser regression test; run with uv run --with playwright pytest tests/test_search_view.py.

Install Chromium with uv run --with playwright playwright install --only-shell chromium.
"""

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

playwright = pytest.importorskip("playwright.sync_api")

STATIC = Path(__file__).resolve().parents[1] / "narratarr" / "static"


@pytest.mark.parametrize("width", [390, 1280])
def test_search_layout_toggle(width):
    title = (
        "The Long Road Home: "
        + "An Illustrated History of the Northern Coast " * 5
        + "AnniversaryEdition" * 4
    )
    items = [
        {
            "title": title,
            "url": "https://example.test/long",
            "format": "MP3",
            "author": "Sam Example",
        },
        {
            "title": "Another book",
            "url": "https://example.test/short",
            "format": "M4B",
            "author": "Pat Example",
        },
    ]
    api = {
        "/api/auth/status": {"user": {"id": 1, "username": "tester", "role": "admin"}},
        "/api/settings": {},
        "/api/sources": [
            {"name": "librivox", "label": "LibriVox", "delivery": "direct", "categories": []}
        ],
        "/api/library": [],
        "/api/follows": [],
    }
    queries = []

    def respond(route):
        url = urlsplit(route.request.url)
        if url.path == "/api/discover":
            queries.append(parse_qs(url.query).get("q", [""])[0])
            route.fulfill(json={"items": items, "page": 1, "total_pages": 1})
        elif url.path in api:
            route.fulfill(json=api[url.path])
        elif url.path == "/":
            route.fulfill(path=STATIC / "index.html")
        elif url.path.startswith("/static/"):
            route.fulfill(path=STATIC / url.path.removeprefix("/static/"))
        else:
            route.fulfill(status=404)

    with playwright.sync_playwright() as pw, pw.chromium.launch() as browser:
        page = browser.new_page(viewport={"width": width, "height": 800})
        page.route("http://narratarr.test/**", respond)
        page.goto("http://narratarr.test/")
        controls = page.get_by_role("group", name="Search results layout")
        result_title = page.locator("#grid .card .title").first
        playwright.expect(result_title).to_have_text(title)
        playwright.expect(controls).to_be_hidden()

        def search():
            field = page.get_by_role("searchbox")
            field.fill("long road")
            field.press("Enter")
            playwright.expect(result_title).to_have_text(title)

        def title_is_clipped():
            return result_title.evaluate("(el) => el.scrollHeight > el.clientHeight")

        search()
        grid = controls.get_by_role("button", name="Grid view")
        listing = controls.get_by_role("button", name="List view")
        playwright.expect(grid).to_have_attribute("aria-pressed", "true")
        assert title_is_clipped()
        page.get_by_role("combobox", name="Format").select_option(label="MP3")

        listing.focus()
        listing.press("Enter")
        playwright.expect(listing).to_have_attribute("aria-pressed", "true")
        playwright.expect(listing).to_be_focused()
        playwright.expect(page.locator("#grid .card")).to_have_count(1)
        assert not title_is_clipped()

        grid.click()
        playwright.expect(grid).to_have_attribute("aria-pressed", "true")
        assert title_is_clipped()
        listing.click()
        assert queries == ["", "long road"]

        page.reload()
        playwright.expect(result_title).to_have_text(title)
        playwright.expect(controls).to_be_hidden()
        assert title_is_clipped()
        search()
        playwright.expect(listing).to_have_attribute("aria-pressed", "true")
        assert not title_is_clipped()
        assert result_title.evaluate("(el) => el.scrollWidth <= el.clientWidth")
        cards = page.locator("#grid .card")
        first, second = cards.nth(0).bounding_box(), cards.nth(1).bounding_box()
        assert first["x"] == second["x"]
        assert second["y"] >= first["y"] + first["height"]
