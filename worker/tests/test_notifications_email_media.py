"""Photos and in-app engagement survive the payload → digest → email boundary."""
from copy import deepcopy
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from notification_fixtures import DIGEST, FIESTA, LINKS, NOW, OPPORTUNITY, notification
from notifications import templates
from notifications.digest import build_items
from notifications.links import Links
from notifications.media import image_urls
from notifications.service import listing_payload


def test_photos_flow_from_stored_listing_to_immediate_and_daily_mail():
    listing = listing_payload(FIESTA)
    assert listing["images"] == image_urls(FIESTA["images"])
    payload = {**OPPORTUNITY.payload, "listing": listing}
    immediate = templates.email(replace(OPPORTUNITY, payload=payload), LINKS, NOW)
    items = build_items([{"kind": "opportunity", "listing_id": 501, "payload": payload}], [], 10)
    daily = templates.email(notification("digest", {"items": items}, listing_id=None), LINKS, NOW)
    for mail, expected_photos in ((immediate, 3), (daily, 1)):
        soup = BeautifulSoup(mail.html, "html.parser")
        photos = [img for img in soup.find_all("img") if not img["src"].startswith("cid:")]
        assert len(photos) == expected_photos
        for img in photos:
            assert img["src"] in listing["images"]
            assert "Ford Fiesta" in img["alt"]
            assert parse_qs(urlsplit(img.parent["href"]).query)["to"] == ["detail"]
        assert soup.find("img", alt="S Auto")["src"] == "cid:ese-auto-logo"
        assert "USD 10.300" in soup.get_text()
        assert "to=listing" not in mail.html
        assert "to=listing" not in mail.text


def test_daily_links_identify_each_listing_and_keep_click_tracking():
    mail = templates.email(DIGEST, LINKS, NOW)
    soup = BeautifulSoup(mail.html, "html.parser")
    clicks = [parse_qs(urlsplit(a["href"]).query) for a in soup.find_all("a")
              if "/r/43" in a["href"]]
    assert {int(q["l"][0]) for q in clicks} == {501, 502, 503, 504}
    assert all(q["to"] == ["detail"] for q in clicks)


def test_old_or_imageless_alerts_keep_price_and_action():
    for value in (None, [], "not an array", [{"url": None}]):
        n = replace(OPPORTUNITY, payload={**OPPORTUNITY.payload, "listing": {**FIESTA, "images": value}})
        mail = templates.email(n, LINKS, NOW)
        soup = BeautifulSoup(mail.html, "html.parser")
        assert "Foto no disponible" in soup.get_text()
        assert "USD 10.300" in soup.get_text()
        assert "Ver auto en Ese Auto" in soup.get_text()
        assert len(soup.find_all("img")) == 1  # the logo still appears


def test_image_urls_are_safe_deduplicated_and_bounded():
    urls = ["javascript:alert(1)", "data:image/png;base64,x", "//host/image.jpg", "/relative.jpg",
            "https:///no-host.jpg", "https://[broken", "https://user:pass@example.test/secret.jpg",
            "https://example.test/a\n.jpg", None, 42, {"url": 123},
            " https://example.test/a.jpg ", {"url": "https://example.test/a.jpg"},
            {"url": "https://example.test/b.jpg?a=1&b=2"}, "http://example.test/c.jpg",
            "https://example.test/d.jpg"]
    assert image_urls(urls) == ["https://example.test/a.jpg", "https://example.test/b.jpg?a=1&b=2",
                                "http://example.test/c.jpg"]
    listing = {**FIESTA, "make": None, "title": 'Auto <b>"especial"</b>',
               "images": ['https://example.test/a.jpg?x=" onerror="bad']}
    mail = templates.email(replace(OPPORTUNITY, payload={"listing": listing}), LINKS, NOW)
    soup = BeautifulSoup(mail.html, "html.parser")
    photo = next(img for img in soup.find_all("img") if not img["src"].startswith("cid:"))
    assert "onerror" not in photo.attrs
    assert 'Auto <b>"especial"</b>' in photo["alt"]


def test_long_digest_is_bounded_with_clear_count_and_complete_text_alternative():
    item = deepcopy(DIGEST.payload["items"][1])
    items = [{**item, "listing_id": n, "listing": {**item["listing"], "id": n}} for n in range(100, 160)]
    n = notification("digest", {"items": items}, id=43, listing_id=None)
    mail = templates.email(n, LINKS, NOW)
    soup = BeautifulSoup(mail.html, "html.parser")
    assert len(soup.find_all("h3")) == 5
    assert "Mostramos 5 de 60 novedades" in soup.get_text()
    assert "60 novedades para revisar" in soup.get_text()
    assert "https://automotive.app/app" in mail.html
    assert len(mail.html.encode()) < 90_000
    assert "https://automotive.app/r/43?to=detail&l=159" in mail.text
    # A development installation without a site cannot hide remaining items.
    untracked = templates.email(n, Links(), NOW)
    assert len(BeautifulSoup(untracked.html, "html.parser").find_all("h3")) == 60


def test_no_base_url_preserves_direct_listing_fallback():
    mail = templates.email(OPPORTUNITY, Links(), NOW)
    soup = BeautifulSoup(mail.html, "html.parser")
    assert all(a["href"] == FIESTA["url"] for a in soup.find_all("a"))
    assert "Ver publicación" in soup.get_text()
