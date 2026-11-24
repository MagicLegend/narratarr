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
            "language": "English",
            "length": "14 hours and 20 minutes",
            "size": "840 MB",
            "bitrate": "128 Kbps",
        },
        {
            "title": "Another book",
            "url": "https://archive.org/details/short",
            "source": "librivox",
            "format": "",
            "author": "Pat Example",
            "length": "37 minutes",
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
    detail_urls = []

    def respond(route):
        url = urlsplit(route.request.url)
        if url.path == "/api/discover":
            queries.append(parse_qs(url.query).get("q", [""])[0])
            route.fulfill(json={"items": items, "page": 1, "total_pages": 1})
        elif url.path == "/api/details":
            detail_urls.append(parse_qs(url.query)["url"][0])
            route.fulfill(
                json={
                    "language": "French",
                    "format": "M4B",
                    "length": "38 minutes",
                    "size": "18 MB",
                    "bitrate": "~66 kbps avg",
                }
            )
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
        sort = page.get_by_role("combobox", name="Sort")
        playwright.expect(sort.locator("option:checked")).to_have_text("Best match")
        sort.scroll_into_view_if_needed()
        sort_box, controls_box = sort.bounding_box(), controls.bounding_box()
        assert sort_box["x"] + sort_box["width"] <= controls_box["x"]
        assert sort_box["y"] < controls_box["y"] + controls_box["height"]
        assert controls_box["y"] < sort_box["y"] + sort_box["height"]
        header_box = controls.locator(
            "xpath=ancestor::div[contains(@class, 'section-head')]"
        ).bounding_box()
        assert controls_box["x"] + controls_box["width"] == pytest.approx(
            header_box["x"] + header_box["width"], abs=1
        )
        grid = controls.get_by_role("button", name="Grid view")
        listing = controls.get_by_role("button", name="List view")
        cards = page.locator("#grid .card")
        facts = cards.first.locator(".facts")
        extra_facts = [
            facts.get_by_text(value, exact=True) for value in ("English", "14h 20m", "128 Kbps")
        ]
        playwright.expect(grid).to_have_attribute("aria-pressed", "true")
        assert title_is_clipped()
        for fact in extra_facts:
            playwright.expect(fact).to_be_hidden()
        page.get_by_role("combobox", name="Format").select_option(label="MP3")

        listing.focus()
        listing.press("Enter")
        playwright.expect(listing).to_have_attribute("aria-pressed", "true")
        playwright.expect(listing).to_be_focused()
        playwright.expect(page.locator("#grid .card")).to_have_count(1)
        assert not title_is_clipped()
        for fact in [*extra_facts, facts.get_by_text("840 MB", exact=True)]:
            playwright.expect(fact).to_be_visible()
        assert facts.evaluate("(el) => el.scrollWidth <= el.clientWidth")

        grid.click()
        playwright.expect(grid).to_have_attribute("aria-pressed", "true")
        assert title_is_clipped()
        listing.click()
        assert queries == ["", "long road"]
        assert detail_urls == []

        page.reload()
        playwright.expect(result_title).to_have_text(title)
        playwright.expect(controls).to_be_hidden()
        assert title_is_clipped()
        search()
        playwright.expect(listing).to_have_attribute("aria-pressed", "true")
        assert not title_is_clipped()
        assert result_title.evaluate("(el) => el.scrollWidth <= el.clientWidth")
        archive_facts = cards.nth(1).locator("[data-list-details]")
        playwright.expect(archive_facts).to_be_visible()
        playwright.expect(archive_facts).to_have_text("French · M4B · 38m · 18 MB · ~66 kbps avg")
        grid.click()
        playwright.expect(archive_facts).to_be_hidden()
        listing.click()
        playwright.expect(archive_facts).to_be_visible()
        assert detail_urls == ["https://archive.org/details/short"]
        first, second = cards.nth(0).bounding_box(), cards.nth(1).bounding_box()
        assert first["x"] == second["x"]
        assert second["y"] >= first["y"] + first["height"]


@pytest.mark.parametrize(
    ("source", "item", "expected"),
    [
        (
            "audible",
            {
                "language": "English",
                "length": "9 hours and 12 minutes",
                "narrators": ["A Narrator"],
                "series": [{"title": "The Series", "sequence": "2"}],
            },
            ["English", "9h 12m", "Narrated by A Narrator", "The Series #2"],
        ),
        ("openlibrary", {"length": "320 pages", "posted": "2002"}, ["320 pages", "2002"]),
        (
            "prowlarr",
            {"format": "MP3", "size": "840 MB", "bitrate": "128 Kbps", "indexer": "Indexer"},
            ["MP3", "840 MB", "128 Kbps", "via Indexer"],
        ),
        (
            "torznab",
            {"format": "M4B", "size": "700 MB", "bitrate": "64 Kbps", "language": "German"},
            ["M4B", "700 MB", "64 Kbps", "German"],
        ),
        (
            "audiobookbay",
            {"format": "MP3", "size": "840 MB", "bitrate": "128 Kbps", "language": "English"},
            ["MP3", "840 MB", "128 Kbps", "English", "21h 2m", "Narrated by A Narrator"],
        ),
    ],
)
def test_provider_list_metadata(source, item, expected):
    results = [
        {"url": "https://example.test/book", "title": "Book", "author": "Author", **item},
        {"url": "https://example.test/other", "title": "Other", "author": "Author"},
    ]
    if source == "audiobookbay":
        results.append(
            {"url": "https://example.test/missing", "title": "Missing", "author": "Author"}
        )
        results.append(
            {
                "url": "https://example.test/complete",
                "title": "Complete",
                "author": "Author",
                "language": "English",
                "format": "MP3",
                "length": "2 hours",
                "size": "100 MB",
                "bitrate": "128 Kbps",
            }
        )
    for book in results:
        book.update(source=source)
        book.setdefault("format", "")
    api = {
        "/api/auth/status": {"user": {"id": 1, "username": "tester", "role": "admin"}},
        "/api/settings": {},
        "/api/sources": [
            {"name": source, "label": source, "delivery": "torrent", "categories": []}
        ],
        "/api/library": [],
        "/api/follows": [],
    }
    detail_urls = []

    def respond(route):
        url = urlsplit(route.request.url)
        if url.path == "/api/discover":
            route.fulfill(json={"items": results, "page": 1, "total_pages": 1})
        elif url.path == "/api/details":
            detail_url = parse_qs(url.query)["url"][0]
            detail_urls.append(detail_url)
            if detail_url.endswith("/other"):
                route.fulfill(status=502, json={"detail": "Unavailable"})
            else:
                route.fulfill(
                    json={
                        "format": "MP3",
                        "language": "English",
                        "size": "840 MB",
                        "bitrate": "128 Kbps",
                        "length": "21 hours and 2 minutes",
                        "narrators": ["A Narrator", "<script>"],
                    }
                )
        elif url.path in api:
            route.fulfill(json=api[url.path])
        elif url.path == "/":
            route.fulfill(path=STATIC / "index.html")
        elif url.path.startswith("/static/"):
            route.fulfill(path=STATIC / url.path.removeprefix("/static/"))
        else:
            route.fulfill(status=404)

    with playwright.sync_playwright() as pw, pw.chromium.launch() as browser:
        page = browser.new_page(viewport={"width": 390, "height": 800})
        page.add_init_script(f'localStorage.setItem("narratarr.source", "{source}")')
        page.route("http://narratarr.test/**", respond)
        page.goto("http://narratarr.test/")
        field = page.get_by_role("searchbox")
        field.fill("book")
        field.press("Enter")
        page.get_by_role("button", name="List view").click()
        cards = page.locator("#grid .card")
        facts = cards.first.locator(".facts")
        for value in expected:
            playwright.expect(facts).to_contain_text(value)
        assert facts.evaluate("(el) => el.scrollWidth <= el.clientWidth")
        if source == "audiobookbay":
            playwright.expect(cards.nth(1).locator("[data-list-details]")).to_have_text(
                "More details unavailable"
            )
            playwright.expect(cards.nth(2).locator("[data-list-details]")).to_have_text(
                "English · MP3 · 21h 2m · 840 MB · 128 Kbps · Narrated by A Narrator, <script>"
            )
            playwright.expect(cards.nth(3).locator(".facts")).to_contain_text("2h")
            assert cards.nth(3).locator("[data-list-details]").count() == 0
            assert sorted(detail_urls) == [
                "https://example.test/book",
                "https://example.test/missing",
                "https://example.test/other",
            ]
            assert cards.nth(2).locator("script").count() == 0
            for value in ("MP3", "840 MB", "128 Kbps", "English"):
                assert facts.inner_text().count(value) == 1
        else:
            assert not detail_urls
