"""Signed email links (docs/AUTENTICACION.md, «Links firmados»): the links of
an email that lead into the app carry &s=<HMAC>, so the web can sign an
email-only account in. Telegram links and links to the source never do."""
from __future__ import annotations

import re
import unittest
from dataclasses import replace

from notifications import templates
from notifications.links import Links, signature
from notification_fixtures import DIGEST, NOW, OPPORTUNITY

SECRET = "alert-link-test-secret-0123456789abcdef"
OWNER = "8d3a7c4e-1f2b-4c5d-9e6f-0a1b2c3d4e5f"
SIGNED = Links("https://automotive.app", SECRET)


def query_of(url: str) -> str:
    return url.split("?", 1)[1] if "?" in url else ""


class SignatureTest(unittest.TestCase):
    def test_matches_the_web(self):
        # The same vectors are in web/lib/alert-session.test.ts.
        self.assertEqual(signature(SECRET, "r", 42, OWNER), "QmbEMrNzw4hGRVgh7FPfPw")
        self.assertEqual(signature(SECRET, "m", 7, OWNER), "txvVh27uBxAp7KCEPptC0w")

    def test_binds_the_scope_the_id_and_the_owner(self):
        base = signature(SECRET, "r", 42, OWNER)
        self.assertNotEqual(signature(SECRET, "m", 42, OWNER), base)
        self.assertNotEqual(signature(SECRET, "r", 43, OWNER), base)
        self.assertNotEqual(signature(SECRET, "r", 42, "another-user"), base)
        self.assertNotEqual(signature(SECRET + "x", "r", 42, OWNER), base)
        self.assertRegex(base, r"^[A-Za-z0-9_-]{22}$")


class LinksTest(unittest.TestCase):
    def test_only_links_into_the_app_with_an_owner_are_signed(self):
        s = signature(SECRET, "r", 42, OWNER)
        self.assertEqual(SIGNED.detail(42, owner=OWNER), f"https://automotive.app/r/42?to=detail&s={s}")
        self.assertEqual(SIGNED.detail(42, 7, owner=OWNER), f"https://automotive.app/r/42?to=detail&l=7&s={s}")
        self.assertEqual(SIGNED.detail(42), "https://automotive.app/r/42?to=detail")
        self.assertEqual(SIGNED.listing(42, "https://x"), "https://automotive.app/r/42?to=listing")
        self.assertEqual(SIGNED.lifecycle(7, owner=OWNER),
                         f"https://automotive.app/m/7?s={signature(SECRET, 'm', 7, OWNER)}")
        self.assertEqual(SIGNED.lifecycle(7), "https://automotive.app/m/7")

    def test_without_a_long_enough_secret_nothing_is_signed(self):
        for links in (Links("https://automotive.app"), Links("https://automotive.app", "short")):
            with self.subTest(secret=links.secret):
                self.assertFalse(links.signs)
                self.assertEqual(links.detail(42, owner=OWNER), "https://automotive.app/r/42?to=detail")
                self.assertEqual(links.lifecycle(7, owner=OWNER), "https://automotive.app/m/7")
        self.assertIsNone(Links("", SECRET).detail(42, owner=OWNER))

    def test_the_secret_never_shows_in_logs(self):
        self.assertNotIn(SECRET, repr(SIGNED))


class TemplatesTest(unittest.TestCase):
    def test_the_email_button_is_signed_for_the_notification_owner(self):
        n = replace(OPPORTUNITY, user_id=OWNER, channel="email")
        mail = templates.email(n, SIGNED, NOW)
        s = signature(SECRET, "r", n.id, OWNER)
        self.assertIn(f"Ver auto en Ese Auto: https://automotive.app/r/42?to=detail&s={s}", mail.text)
        self.assertIn(f"https://automotive.app/r/42?to=detail&amp;s={s}", mail.html)
        # The link to the source stays unsigned: it never signs anyone in.
        for url in re.findall(r"https://automotive\.app/r/42\?to=listing[^\"\s<]*", mail.text + mail.html):
            self.assertNotIn("s=", query_of(url))

    def test_every_digest_item_of_an_email_is_signed(self):
        n = replace(DIGEST, user_id=OWNER, channel="email")
        text = templates.email(n, SIGNED, NOW).text
        s = signature(SECRET, "r", n.id, OWNER)
        for listing_id in (501, 502, 503, 504):
            self.assertIn(f"https://automotive.app/r/43?to=detail&l={listing_id}&s={s}", text)

    def test_telegram_is_never_signed(self):
        n = replace(OPPORTUNITY, user_id=OWNER)
        tg = templates.telegram(n, SIGNED, NOW)
        urls = [b.url for row in tg.buttons for b in row if b.url] + re.findall(r'href="([^"]+)"', tg.text)
        self.assertTrue(urls)
        for url in urls:
            self.assertNotIn("s=", query_of(url))
        self.assertNotIn("s=", templates.telegram(replace(DIGEST, user_id=OWNER), SIGNED, NOW).text)

    def test_the_plan_email_button_is_signed_for_its_user(self):
        row = {"id": 7, "user_id": OWNER, "kind": "trial_ended", "payload": {"model": "Fiesta"},
               "unsubscribe_token": "3f0c1a52-6c55-4a43-9f39-0d8f3c7c2b11"}
        mail = templates.lifecycle_email(row, SIGNED, NOW)
        self.assertIn(f"https://automotive.app/m/7?s={signature(SECRET, 'm', 7, OWNER)}", mail.text)


if __name__ == "__main__":
    unittest.main()


def test_open_pixel_marks_the_email_by_kind():
    links = Links("https://eseauto.com.ar", "")
    assert links.open_pixel("n", 42) == "https://eseauto.com.ar/o/42?k=n"
    assert links.open_pixel("m", 7) == "https://eseauto.com.ar/o/7?k=m"
    assert Links("").open_pixel("n", 42) is None
