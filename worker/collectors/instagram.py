"""Recent public posts from two classifieds accounts, using Instagram's web page.

Only the requested post's caption is an ad. Embedded web data is read from the
HTML, never from private API endpoints; comments, recommendations and truncated
Open Graph quotations are not a substitute. A local Playwright storage state is
optional. The bounded profile feed is discovery, not a historical inventory.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import config
from normalization.description_facts import parse as description_facts
from normalization.money import plausible_vehicle_price
from ._browser import browser_context
from ._http import Page, slim_html, soup
from ._regional import matches_vehicle, timestamp
from .base import BaseScraper, CollectorBlocked, Listing, ListingDetail


BASE = "https://www.instagram.com"
_POST = re.compile(r"^/(?:(?P<account>[\w.]+)/)?(?P<kind>p|reel)/(?P<code>[\w-]+)/?$")
_BRANDS = re.compile(r"\b(?:alfa romeo|audi|bmw|byd|changan|chery|chevrolet|citroen|dodge|"
                     r"ds|fiat|ford|geely|genesis|haval|honda|hyundai|isuzu|jac|jeep|kia|land rover|"
                     r"lexus|lifan|mercedes(?: benz)?|mini|mitsubishi|nissan|peugeot|porsche|"
                     r"ram|renault|seat|smart|subaru|suzuki|toyota|volkswagen|volvo|vw)\b")
_WALL_TEXT = ("log in to see", "login to see", "inicia sesion para ver", "iniciar sesion para ver",
              "please wait a few minutes", "espera unos minutos", "confirm you're human",
              "confirma que eres humano", "regístrate en instagram para estar siempre al día")


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) not in ("Mn", "Cf"))


def _post(url: str) -> tuple[str | None, str, str]:
    parsed = urlparse(urljoin(BASE, url))
    if parsed.hostname not in {"instagram.com", "www.instagram.com"}:
        raise ValueError("Instagram URL outside the source")
    match = _POST.fullmatch(parsed.path)
    if not match:
        raise ValueError("Instagram URL is not a post or reel")
    return match["account"], match["kind"], match["code"]


def _walk(data):
    """Objects in public JSON script blocks, including Relay's nested arrays."""
    stack = [data]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            yield value
            stack.extend(reversed(list(value.values())))
        elif isinstance(value, list):
            stack.extend(reversed(value))


def _objects(doc):
    decoder = json.JSONDecoder()
    for tag in doc.select("script"):
        text = (tag.string or "").strip()
        if (tag.get("type") or "").lower() in {"application/json", "application/ld+json"}:
            candidate = text
        elif (match := re.match(r"(?:window\.)?_sharedData\s*=\s*", text)):
            candidate = text[match.end():]
        else:
            continue
        try:
            if (tag.get("type") or "").lower() in {"application/json", "application/ld+json"}:
                data = json.loads(candidate)
            else:
                data, _ = decoder.raw_decode(candidate)
        except (TypeError, ValueError):
            continue
        yield from _walk(data)


def _owner(node: dict) -> str | None:
    owner = node.get("owner") or node.get("user")
    return owner.get("username") if isinstance(owner, dict) else None


def _caption(node: dict) -> str | None:
    caption = node.get("caption")
    if isinstance(caption, dict):
        return caption.get("text")
    if isinstance(caption, str):
        return caption
    edges = (node.get("edge_media_to_caption") or {}).get("edges", [])
    if edges:
        return (edges[0].get("node") or {}).get("text")
    # An explicit empty caption is a known non-ad, not a broken parser.
    if "caption" in node or "edge_media_to_caption" in node:
        return ""
    return None


def _images(node: dict) -> list[str]:
    children = node.get("carousel_media") or []
    edges = (node.get("edge_sidecar_to_children") or {}).get("edges", [])
    children = children or [edge.get("node") for edge in edges]
    if children:
        return list(dict.fromkeys(url for child in children if isinstance(child, dict)
                                  for url in _images(child)))
    url = node.get("display_url") or node.get("display_uri")
    if not url:
        candidates = (node.get("image_versions2") or {}).get("candidates") or []
        candidates = [c for c in candidates if isinstance(c, dict) and c.get("url")]
        if candidates:
            best = max(candidates, key=lambda c: (c.get("width") or 0) * (c.get("height") or 0))
            url = best["url"]
    return [url] if isinstance(url, str) and url.startswith("https://") else []


def _published(node: dict) -> int | None:
    value = node.get("taken_at_timestamp") or node.get("taken_at")
    if isinstance(value, (int, float)) and value > 1_000_000_000:
        return int(value)
    return timestamp(node.get("datePublished"))


def _wall(doc, url: str) -> bool:
    path = urlparse(url).path
    if any(part in path for part in ("/accounts/login", "/challenge", "/checkpoint")):
        return True
    if doc.select_one("input[name='password'], form[action*='/accounts/login']"):
        return True
    text = _plain(doc.get_text(" ", strip=True))
    return any(_plain(phrase) in text for phrase in _WALL_TEXT)


def _sold(caption: str) -> bool:
    lines = [_plain(line).strip(" \t-•*#.!✅☑️🚘🚗") for line in caption.splitlines() if line.strip()]
    return bool(lines and re.match(r"^vendid[oa]\b", lines[0])) or any(
        re.fullmatch(r"(?:(?:estado|status)\s*:\s*)?vendid[oa]", line) for line in lines)


def _title(caption: str) -> str:
    for line in caption.splitlines():
        line = line.strip(" \t-•*🚘🚗🏁✅")
        # "Modelo: Peugeot ..." is a caption label, not structured make/model.
        line = re.sub(r"(?i)^modelo\s*:\s*", "", line)
        if _BRANDS.search(_plain(line)):
            return line[:200]
    return ""


def _label(caption: str, pattern: str) -> str | None:
    for line in caption.splitlines():
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            return match[1].strip() or None
    return None


class InstagramIdentityError(RuntimeError):
    """A discovered link belongs to another author; never a removal proof."""


class InstagramScraper(BaseScraper):
    INVENTORY_TARGET = True
    DETAIL_PARSER_VERSION = 1
    account = ""
    MAX_SCROLLS = 6
    SETTLE_MS = 2_500

    def __init__(self, *, storage_state: str | None = None, max_posts: int | None = None):
        self.storage_state = storage_state if storage_state is not None else getattr(config, "INSTAGRAM_STORAGE_STATE", "")
        self.max_posts = max(1, min(60, int(max_posts if max_posts is not None
                                          else getattr(config, "INSTAGRAM_MAX_POSTS", 24))))

    @classmethod
    def _check_status(cls, status: int) -> None:
        if status in {401, 403, 429}:
            raise CollectorBlocked(f"{cls.name}: Instagram HTTP {status}")
        if status not in {200, 404, 410}:
            raise RuntimeError(f"{cls.name}: Instagram HTTP {status}")

    @classmethod
    def _media(cls, doc, code: str) -> dict | None:
        matches = []
        other_owner = False
        for node in _objects(doc):
            if (node.get("shortcode") or node.get("code")) != code:
                continue
            owner = _owner(node)
            if owner and owner.lower() != cls.account:
                other_owner = True
                continue
            if owner and _caption(node) is not None:
                matches.append(node)
        if matches:
            return max(matches, key=lambda node: (len(_caption(node) or ""), len(_images(node)), bool(_published(node))))
        if other_owner:
            raise InstagramIdentityError(f"{cls.name}: post author does not match @{cls.account}")
        return None

    @classmethod
    def _social_post(cls, doc, code: str) -> dict | None:
        for node in _objects(doc):
            if node.get("@type") != "SocialMediaPosting" or not isinstance(node.get("articleBody"), str):
                continue
            link = node.get("url") or node.get("mainEntityOfPage")
            if isinstance(link, dict):
                link = link.get("@id")
            try:
                _, _, linked_code = _post(link or "")
            except ValueError:
                continue
            if linked_code != code:
                continue
            author = node.get("author")
            if not isinstance(author, dict):
                continue
            author_url = author.get("url")
            owner = author.get("alternateName") or author.get("identifier") or author.get("name")
            if author_url:
                parsed = urlparse(urljoin(BASE, author_url))
                owner = parsed.path.strip("/") if parsed.hostname in {"instagram.com", "www.instagram.com"} else None
            if isinstance(owner, str) and owner.lstrip("@").lower() == cls.account:
                return node
            raise InstagramIdentityError(f"{cls.name}: structured post author does not match")
        return None

    @classmethod
    def _dom_post(cls, doc, code: str) -> dict | None:
        canonical = doc.select_one("link[rel='canonical']")
        try:
            _, _, canonical_code = _post(canonical.get("href", "") if canonical else "")
        except ValueError:
            return None
        if canonical_code != code:
            return None
        # The current public desktop caption is a span, legacy pages use h1.
        # Keep its own author/time row as the scope; never the whole main text.
        for caption in doc.select("main h1, [role='main'] h1, main span.x126k92a, [role='main'] span.x126k92a"):
            for row in caption.parents:
                if row.name in {"main", "body", "html"} or row.get("role") == "main":
                    break
                author = next((a for a in row.select("a[href]")
                               if a.get_text(strip=True) == cls.account
                               and urlparse(urljoin(BASE, a["href"])).hostname in {"instagram.com", "www.instagram.com"}
                               and urlparse(urljoin(BASE, a["href"])).path == f"/{cls.account}/"), None)
                date = row.select_one("time[datetime]")
                if author is None or date is None:
                    continue
                # BeautifulSoup doesn't turn <br> into newlines with separator="".
                copy = soup(str(caption))
                for br in copy.select("br"):
                    br.replace_with("\n")
                caption_text = copy.get_text("", strip=False).strip()
                images = []
                for media_scope in row.parents:
                    images = [img.get("src") for img in media_scope.select("._aagv img[src]")]
                    if images or media_scope.name == "main":
                        break
                return {"articleBody": caption_text, "datePublished": date["datetime"], "image": images}
        return None

    @classmethod
    def parse_detail(cls, html: str, url: str, status: int = 200) -> ListingDetail:
        cls._check_status(status)
        if status in {404, 410}:
            return ListingDetail(url, gone=True, gone_reason=str(status))
        if any(part in urlparse(url).path for part in ("/accounts/login", "/challenge", "/checkpoint")):
            raise CollectorBlocked(f"{cls.name}: Instagram login or challenge")
        account, kind, code = _post(url)
        if account and account.lower() != cls.account:
            raise InstagramIdentityError(f"{cls.name}: URL author does not match")
        doc = soup(html)
        canonical = doc.select_one("link[rel='canonical']")
        if canonical:
            try:
                _, _, canonical_code = _post(canonical.get("href", ""))
            except ValueError:
                canonical_code = None
            if canonical_code and canonical_code != code:
                raise RuntimeError(f"{cls.name}: canonical URL belongs to a different post")
        media = cls._media(doc, code)
        social = None if media is not None else cls._social_post(doc, code) or cls._dom_post(doc, code)
        if media is None and social is None:
            if _wall(doc, url):
                raise CollectorBlocked(f"{cls.name}: Instagram requires login or verification")
            raise RuntimeError(f"{cls.name}: cannot verify complete caption for post {code}")
        caption = (_caption(media) if media is not None else social["articleBody"]) or ""
        if _sold(caption):
            return ListingDetail(url, gone=True, gone_reason="vendido")
        title = _title(caption)
        facts = description_facts(caption)
        if not facts or not title or re.search(r"(?i)#(?:meme|humor)\b", caption):
            return ListingDetail(url)
        year = facts.year
        if year is None and (match := re.search(r"\b(19[89]\d|20[0-3]\d)\b", title)):
            candidate = int(match[1])
            year = candidate if candidate <= datetime.now().year + 1 else None
        selected = None
        for category in ("cash", "generic", "list", "down_payment", "installment"):
            amounts = {(a.amount, a.currency): a for a in facts.of_kind(category)
                       if plausible_vehicle_price(a.amount, a.currency)}
            if len(amounts) == 1:
                selected = next(iter(amounts.values()))
                break
        partial = bool(selected and selected.kind in {"down_payment", "installment"})
        if not ((year is not None and facts.mileage_km is not None) or (selected and not partial)):
            return ListingDetail(url)
        location = _label(caption, r"(?:ubicaci[oó]n\s*:\s*|📍\s*(?:ubicaci[oó]n\s*:\s*)?)([^\n]+)")
        seller = _label(caption, r"^[^\w@]*(?:vendedor|propietario|contacto|instagram)\s*:\s*([^\n]+)")
        images = _images(media) if media is not None else social.get("image") or []
        if isinstance(images, str):
            images = [images]
        images = [value if isinstance(value, str) else value.get("url") for value in images
                  if isinstance(value, (str, dict))]
        structured = social.get("about") if social else None
        structured = structured if isinstance(structured, dict) and structured.get("@type") == "Car" else {}
        brand = structured.get("brand")
        brand = brand.get("name") if isinstance(brand, dict) else brand
        listing = Listing(
            source=cls.name, listing_id=code, titulo=title,
            url=f"{BASE}/{cls.account}/{kind}/{code}/",
            precio=selected.amount if selected else None, moneda=selected.currency if selected else None,
            marca=brand, modelo=structured.get("model"), anio=year, km=facts.mileage_km,
            ubicacion=location, combustible=facts.fuel, transmision=facts.transmission,
            published_at=_published(media if media is not None else social),
            descripcion=caption, imagenes=list(dict.fromkeys(u for u in images if u)),
            vendedor_nombre=seller, price_partial=partial,
            price_partial_reason=f"{selected.kind} (instagram)" if partial else None,
            extra={"instagram_account": cls.account, "discovery_scope": "recent_profile_feed"},
        )
        return ListingDetail(url, listing=listing)

    def slim_page(self, page: Page) -> str:
        # Relay/public media payloads use both 'code' and legacy 'shortcode'.
        return slim_html(page.html, scripts_with="caption")

    @classmethod
    def profile_post_urls(cls, html: str) -> list[str]:
        doc = soup(html)
        out = {}
        sold = set()
        for node in _objects(doc):
            if (_owner(node) or "").lower() == cls.account and (code := node.get("shortcode") or node.get("code")):
                if _sold(_caption(node) or ""):
                    sold.add(code)
                    continue
                kind = "reel" if node.get("product_type") == "clips" else "p"
                out[code] = f"{BASE}/{cls.account}/{kind}/{code}/"
        for anchor in doc.select("main a[href], [role='main'] a[href]"):
            try:
                account, kind, code = _post(anchor["href"])
            except ValueError:
                continue
            if account and account.lower() != cls.account:
                continue
            if code in sold:
                continue  # Old sold pins should not consume the recent-post budget.
            out.setdefault(code, f"{BASE}/{cls.account}/{kind}/{code}/")
        for code in sold:
            out.pop(code, None)
        if out:
            return list(out.values())
        if sold:
            return []  # A verified feed consisting entirely of sold posts.
        if _wall(doc, f"{BASE}/{cls.account}/"):
            raise CollectorBlocked(f"{cls.name}: Instagram profile requires login or verification")
        main = doc.select_one("main, [role='main']")
        if main and any(text in _plain(main.get_text(" ", strip=True))
                        for text in ("no posts yet", "aun no hay publicaciones")):
            return []
        raise RuntimeError(f"{cls.name}: unrecognized Instagram profile feed")

    async def _load(self, page, url: str) -> Page:
        response = await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
        status = response.status if response else 0
        self._check_status(status)
        await page.wait_for_timeout(self.SETTLE_MS)
        result = Page(status, page.url, await page.content())
        if urlparse(result.url).hostname not in {"instagram.com", "www.instagram.com"}:
            raise CollectorBlocked(f"{self.name}: unexpected Instagram redirect")
        if any(part in urlparse(result.url).path for part in ("/accounts/login", "/challenge", "/checkpoint")):
            raise CollectorBlocked(f"{self.name}: Instagram login or verification redirect")
        return result

    def _state(self) -> str | None:
        if self.storage_state and not Path(self.storage_state).is_file():
            raise RuntimeError(f"{self.name}: configured INSTAGRAM_STORAGE_STATE file is missing")
        return self.storage_state or None

    async def fetch_detail_page(self, url: str) -> Page:
        _post(url)
        async with browser_context(storage_state=self._state()) as context:
            page = await context.new_page()
            try:
                result = await self._load(page, url)
                if result.status == 200 and _post(result.url)[2] != _post(url)[2]:
                    raise RuntimeError(f"{self.name}: redirected to a different Instagram post")
                return result
            finally:
                await page.close()

    async def search(self, filters: dict) -> list[Listing]:
        async with browser_context(storage_state=self._state()) as context:
            profile = await context.new_page()
            detail = await context.new_page()
            try:
                page = await self._load(profile, f"{BASE}/{self.account}/")
                if page.status != 200:
                    raise RuntimeError(f"{self.name}: profile unavailable (HTTP {page.status})")
                urls = dict.fromkeys(self.profile_post_urls(page.html))
                stalled = 0
                for _ in range(self.MAX_SCROLLS):
                    if len(urls) >= self.max_posts:
                        break
                    await profile.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await profile.wait_for_timeout(900)
                    previous = len(urls)
                    urls.update(dict.fromkeys(self.profile_post_urls(await profile.content())))
                    stalled = stalled + 1 if len(urls) == previous else 0
                    if stalled >= 2:
                        break
                out = {}
                verified = 0
                for url in list(urls)[:self.max_posts]:
                    raw = await self._load(detail, url)
                    if raw.status == 200 and _post(raw.url)[2] != _post(url)[2]:
                        raise RuntimeError(f"{self.name}: redirected to a different Instagram post")
                    try:
                        parsed = self.parse_detail(raw.html, url, raw.status)
                    except InstagramIdentityError:
                        continue  # A recommendation is not this account's inventory.
                    verified += 1
                    if parsed.listing and matches_vehicle(parsed.listing, filters):
                        out[parsed.listing.listing_id] = parsed.listing
                if urls and not verified:
                    raise RuntimeError(f"{self.name}: no discovered posts belonged to the source account")
                return list(out.values())
            finally:
                await detail.close()
                await profile.close()


class OnlyCarsUsadosScraper(InstagramScraper):
    name = "onlycarsusados"
    account = "onlycarsusados"


class SCClasificadosScraper(InstagramScraper):
    name = "sc_clasificados"
    account = "sc_clasificados"
