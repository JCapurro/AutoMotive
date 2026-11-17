"""worker/prospector: phones, hard rules, sellers, facts and the write/review loop (no database, no CLI)."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from prospector import claude, facts as F, lookup, phones, rules, run, sellers, writer
from prospector.sellers import Prospect, Seller

NOW = datetime(2026, 11, 15, 13, 0, tzinfo=timezone.utc)


# ----------------------------------------------------------------------------- phones

@pytest.mark.parametrize("raw, want", [
    ("+54 9 11 5555-1234", "5491155551234"),
    ("011 15 5555 1234", "5491155551234"),
    ("341 15 512-3456", "5493415123456"),
    ("0341-155123456", "5493415123456"),
    ("3415123456", "5493415123456"),
    ("5493415123456", "5493415123456"),
    ("1111111111", None),
    ("12500000", None),
    ("4155123456", None),          # no area code starts with 4
])
def test_normalize(raw, want):
    assert phones.normalize(raw) == want


def test_find_in_text_skips_prices_and_km():
    text = "Precio $ 12.500.000. Tiene 135000 km. Año 2016. Consultas al WhatsApp 341 15 512-3456"
    assert phones.find_in_text(text) == ["5493415123456"]


def test_find_in_text_needs_a_contact_word_or_a_phone_shape():
    assert phones.find_in_text("Motor 1.6 16v 3415123456 unidades") == []
    assert phones.find_in_text("cel 3415123456") == ["5493415123456"]
    assert phones.find_in_text("llamame al 0341 155123456") == ["5493415123456"]
    assert phones.find_in_text("https://wa.me/5491155551234") == ["5491155551234"]


def test_best_of_prefers_the_repeated_number_and_skips_banned():
    texts = ["wsp 3415123456", "wsp 3415123456", "tel 1155551234"]
    assert phones.best_of(texts) == "5493415123456"
    assert phones.best_of(texts, banned=frozenset({"5493415123456"})) == "5491155551234"


def test_rosariogarage_page_reads_the_seller_link_not_the_site():
    html = ('<a href="https://wa.me/5493413286853?text=Hola!">sitio</a>'
            '<a class="whatsapp" href="https://wa.me/5493413100940?text=Hola *CIO+Motors*, te contacto por esta">')
    assert phones.from_rosariogarage_page(html) == "5493413100940"
    assert phones.from_rosariogarage_page('<a href="https://wa.me/5493413286853?text=Hola!">') is None


def test_wa_link_encodes_the_text():
    assert phones.wa_link("5493415123456", "Hola, ¿todo bien?") == \
        "https://wa.me/5493415123456?text=Hola%2C%20%C2%BFtodo%20bien%3F"


# ----------------------------------------------------------------------------- rules

FACTS = {"stock": {"avisos_activos": 7}, "ganchos": [{"auto": "Toyota Etios 2015", "precio_publicado": "$11.900.000",
                                                      "porcentaje_abajo_de_comparables": 17, "cantidad_de_comparables": 42,
                                                      "url": "https://x/MLA-1234567", "listing_id": 99}]}
GOOD = ("Hola, Autos del Parque Demo. Soy Juan, armé Ese Auto: aviso cuando sale un usado por debajo de los parecidos.\n\n"
        "Vi que tenés 7 autos publicados. Hoy un particular publicó un Toyota Etios 2015 en Rosario a $11.900.000, "
        "17 % abajo de 42 parecidos.\n\n¿Te lo paso?")


def test_a_good_message_passes():
    assert rules.check(GOOD, FACTS) == []


@pytest.mark.parametrize("change, problem", [
    (lambda t: t.replace("42", "43"), "números que no están en los hechos: 43"),
    (lambda t: t.replace("¿Te lo paso?", "Mirá www.eseauto.com.ar ¿Te lo paso?"), "tiene un link"),
    (lambda t: t.replace("Hoy", "Con IA hoy"), "menciona IA"),
    (lambda t: t + " ¿Te sirve?", "hace más de una pregunta"),
    (lambda t: t.replace("¿Te lo paso?", "¿Te lo paso? Saludos"), "la pregunta no va al final"),
    (lambda t: t.replace("Soy Juan", "Me llamo Pedro"), "Juan no se presenta"),
    (lambda t: t.replace("publicados", "vendidos"), "dice vendido"),
    (lambda t: t.replace("Hoy", "El plan Pro sale por mes. Hoy"), "menciona el precio del plan"),
    (lambda t: t.replace("tenés", "tienes"), "usa tuteo en vez de voseo"),
    (lambda t: t + "🚗🔥", "tiene más de un emoji"),
    (lambda t: t.replace("\n\n¿", "\n\nOk.\n\n¿").replace("publicados.", "publicados.\n\nY"), "párrafos"),
])
def test_rules_catch(change, problem):
    assert any(problem in p for p in rules.check(change(GOOD), FACTS))


def test_too_long():
    assert any("caracteres" in p for p in rules.check(GOOD + " " + "a" * 300 + "?", FACTS))


def test_numbers_from_urls_and_ids_are_not_sayable():
    assert "1234567" not in rules.allowed_numbers(FACTS)
    assert "99" not in rules.allowed_numbers(FACTS)
    assert {"11900000", "17", "42", "7", "2015"} <= rules.allowed_numbers(FACTS)


# ----------------------------------------------------------------------------- sellers

def row(i, source="facebook", name="Autos Perez", make="Toyota", model="Etios", year=2015, price=11_900_000, **kw):
    base = {"id": i, "source": source, "seller_name": name, "make": make, "model": model, "trim": None, "year": year,
            "price": price, "currency": "ARS", "price_usd": price / 1000, "seller_type": None, "dealer_inferred": False,
            "title": f"{make} {model}", "description": "", "url": f"https://x/{i}", "first_seen_at": NOW - timedelta(days=10),
            "published_at": None, "province_id": "82", "department": "Rosario", "precision": "locality",
            "lat": -32.95, "lon": -60.65, "mileage_km": 90000}
    base.update(kw)
    return base


def test_group_sellers_keeps_3_to_60():
    rows = [row(i, name="A") for i in range(3)] + [row(10 + i, name="B") for i in range(2)]
    assert [s.name for s in sellers.group_sellers(rows)] == ["A"]


def test_profiles_with_two_identical_listings_are_one_prospect():
    a = [row(1, name="Perfil Uno", year=2015, price=1), row(2, name="Perfil Uno", year=2016, price=2),
         row(3, name="Perfil Uno", year=2018, price=3)]
    b = [row(4, name="Perfil Dos", year=2015, price=1), row(5, name="Perfil Dos", year=2016, price=2),
         row(6, name="Perfil Dos", year=2020, price=9)]
    c = [row(7, name="Otro", year=2015, price=1), row(8, name="Otro", year=2011, price=5), row(9, name="Otro", year=2012, price=6)]
    groups = sellers.merge_duplicates(sellers.group_sellers(a + b + c))
    assert sorted(len(g) for g in groups) == [1, 2]


def test_a_shared_phone_joins_profiles():
    s = sellers.group_sellers([row(i, name="X", year=2000 + i) for i in range(3)] +
                              [row(10 + i, name="Y", year=1990 + i) for i in range(3)])
    groups = sellers.merge_duplicates(s, phone_of={"facebook|X": "5493415123456", "facebook|Y": "5493415123456"})
    assert len(groups) == 1


@pytest.mark.parametrize("name, reason", [("Kavak", "cadena u oficial"), ("Tienda Oficial Toyota", "cadena u oficial"),
                                          ("Plan de Ahorro Fiat", "cadena u oficial"), ("Autos Perez", None)])
def test_exclusions(name, reason):
    p = Prospect([Seller("mercadolibre", name, [row(1, name=name)])])
    assert sellers.exclusion_reason(p) == reason


def test_plan_text_excludes():
    rs = [row(i, description="Plan de ahorro adjudicado, cuota 1") for i in range(3)]
    assert sellers.exclusion_reason(Prospect([Seller("facebook", "Juan Gomez", rs)])) == "plan de ahorro"


def test_classify():
    person = Prospect([Seller("facebook", "Juan Gomez", [row(i) for i in range(3)])])
    assert sellers.classify(person) == "persona"
    assert sellers.classify(Prospect([Seller("facebook", "Gomez Automotores", [row(1)])])) == "agencia"
    dealer = Prospect([Seller("deruedas", "Juan Gomez", [row(i, seller_type="dealer") for i in range(3)])])
    assert sellers.classify(dealer) == "agencia"


def test_first_name_only_for_people_with_a_real_name():
    p = Prospect([Seller("facebook", "Juan Gomez", [row(1)])], kind="persona")
    assert sellers.first_name(p) == "Juan"
    assert sellers.first_name(Prospect([Seller("facebook", "juancho_77", [row(1)])], kind="persona")) is None
    assert sellers.first_name(Prospect([Seller("facebook", "Juan Gomez", [row(1)])], kind="agencia")) is None


def test_already_contacted(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps([{"name": "Autos Perez", "source": "Marketplace", "url": "https://x/77", "also": "Perez Dos"}]),
                    encoding="utf-8")
    c = sellers.load_contacted(path)
    assert sellers.already_contacted(Prospect([Seller("facebook", "Autos Perez", [row(1)])]), c)
    assert sellers.already_contacted(Prospect([Seller("facebook", "Perez Dos", [row(1)])]), c)
    # A business name contacted on another portal is the same business.
    assert sellers.already_contacted(Prospect([Seller("mercadolibre", "Autos Perez", [row(1)])]), c)
    assert sellers.already_contacted(Prospect([Seller("deruedas", "Nadie", [row(77)])]), c)
    assert not sellers.already_contacted(Prospect([Seller("deruedas", "Nadie", [row(1)])]), c)
    assert sellers.load_contacted(tmp_path / "missing.json").names == frozenset()


def test_build_prospects_reads_the_phone_of_the_listing():
    rows = [row(i, name="Juan Gomez", year=2010 + i, description="wsp 3415123456" if i == 0 else "") for i in range(3)]
    out, dropped = sellers.build_prospects(rows, contacted=sellers.Contacted(frozenset(), frozenset(), frozenset()))
    assert [(p.phone, p.phone_source, p.kind) for p in out] == [("5493415123456", "aviso", "persona")]


def test_shared_phones():
    rows = [row(i, name=f"S{i}", description="tel 3415123456") for i in range(5)]
    assert sellers.shared_phones(rows) == frozenset({"5493415123456"})


# ----------------------------------------------------------------------------- facts

def hook_row(i, *, diff=17.0, n=42, dept="Rosario", prov="82", price=11_900_000, description="", **kw):
    kw.setdefault("images", ["a", "b", "c", "d", "e"])
    r = row(i, seller_name="Particular", description=description, province_id=prov, department=dept,
            first_seen_at=NOW - timedelta(hours=5), price=price, **kw)
    r["ref"] = {"n": n, "diff_pct": diff}
    return r


def prospect_rosario():
    return Prospect([Seller("rosariogarage", "Autos del Parque Demo", [row(i, name="Autos del Parque Demo", year=2010 + i) for i in range(4)])],
                    kind="agencia")


@pytest.mark.parametrize("change, ok", [
    ({}, True),
    ({"diff": 9.0}, False),          # below 10 %
    ({"diff": 40.0}, False),         # a typo more often than a deal
    ({"n": 5}, False),               # too few comparables
    ({"price": 11_111_111}, False),  # placeholder price
    ({"description": "Financiamos y tomamos usados"}, False),   # writes like an agency
    ({"model": "Corolla"}, False),   # not one of their models
    ({"prov": "14", "dept": "Capital"}, False),                 # another region
])
def test_hook_candidates(change, ok):
    p = prospect_rosario()
    zone = F.zone_of(p.listings, None)
    got = F.hook_candidates([hook_row(100, **change)], p, zone, None)
    assert bool(got) is ok


def test_hooks_closer_first_and_exclusions():
    p = prospect_rosario()
    zone = F.zone_of(p.listings, None)
    pool = [hook_row(100, dept="Santa Fe", diff=22), hook_row(101, dept="Rosario", diff=12)]
    got = F.hook_candidates(pool, p, zone, None)
    assert [c["row"]["id"] for c in got] == [101, 100]
    assert [c["row"]["id"] for c in F.hook_candidates(pool, p, zone, None, exclude=[101])] == [100]


def test_when_published():
    art = timezone(timedelta(hours=-3))
    now = datetime(2026, 11, 15, 10, 0, tzinfo=art)
    assert F.when_published(now - timedelta(hours=2), now) == "hoy"
    assert F.when_published(now - timedelta(hours=20), now) == "ayer"
    assert F.when_published(now - timedelta(hours=40), now) == "anteayer"


def test_position_counts_only_the_zone():
    zone = F.Zone("82", "Rosario", "litoral")
    pool = [{"price_usd": 10, "province_id": "82"}, {"price_usd": 20, "province_id": "82"},
            {"price_usd": 5, "province_id": "14"}]
    assert F.position(pool, 15, zone) == {"n": 2, "cheaper": 1}
    amba = F.Zone("06", "Morón", "amba")
    pool = [{"price_usd": 10, "province_id": "02"}, {"price_usd": 10, "province_id": "06", "department": "Morón"},
            {"price_usd": 10, "province_id": "06", "department": "Bahía Blanca"}]
    assert F.position(pool, 20, amba)["n"] == 2


def test_build_formats_numbers_for_the_writer():
    p = prospect_rosario()
    pool_peers = [{"price_usd": 5000 + 100 * i, "province_id": "82"} for i in range(10)]
    looks = F.Lookups(pool=lambda _id: pool_peers, demand=lambda *a: 4, stopped=lambda keys: 2)
    out = F.build(p, pool=[hook_row(100)], zone_map=None, lookups=looks, now=NOW)
    assert out["ganchos"][0]["precio_publicado"] == "$11.900.000"
    assert out["ganchos"][0]["porcentaje_abajo_de_comparables"] == 17
    assert out["ganchos"][0]["publicado"] == "hoy"
    assert out["dejaron_de_publicarse"] == {"avisos": 2, "en_los_ultimos_dias": 30}
    assert out["demanda_agregada"][0]["busquedas_activas_en_ese_auto"] == 4
    assert out["stock"]["avisos_activos"] == 4
    assert out["prospecto"]["zona"] == "Rosario, Santa Fe"


def test_demand_below_the_minimum_is_not_said():
    p = prospect_rosario()
    looks = F.Lookups(pool=lambda _id: [], demand=lambda *a: 2, stopped=lambda keys: 0)
    assert F.build(p, pool=[], zone_map=None, lookups=looks, now=NOW)["demanda_agregada"] == []


def test_money():
    assert F.money(11900000, "ARS") == "$11.900.000"
    assert F.money(16800, "USD") == "US$ 16.800"


# ----------------------------------------------------------------------------- writer

def fake_call(drafts, reviews):
    """Answers the writer and the reviewer in turn, recording what they were sent."""
    sent = []

    def call(c: claude.Call):
        sent.append(c)
        payload = json.loads(c.user)
        ids = [p["prospecto"] for p in payload["prospectos"]]
        if c.system == writer.WRITER_SYSTEM:
            return {"mensajes": [{"prospecto": i, "variantes": drafts.pop(0)} for i in ids]}
        return {"revisiones": [{"prospecto": i, **reviews.pop(0)} for i in ids]}
    return call, sent


def variants(a=GOOD, b=GOOD.replace("17 %", "17 %")):
    return [{"tipo_gancho": "oportunidad", "texto": a}, {"tipo_gancho": "stock_viejo", "texto": b}]


def ok(i=0):
    return {"decision": "elegir", "variante_elegida": i, "problemas": [], "instrucciones": "", "por_que": "bien"}


def test_write_all_chooses():
    job = writer.Job("p1", FACTS)
    call, sent = fake_call([variants()], [ok(1)])
    writer.write_all([job], examples=[], call=call, log=lambda m: None)
    assert job.chosen == 1 and job.hook_type == "stock_viejo" and not job.dropped
    # The writer never sees URLs or ids.
    assert "https://x" not in sent[0].user and "listing_id" not in sent[0].user
    assert sent[0].model == writer.WRITER_MODEL and sent[0].effort == "high"


def test_a_choice_that_breaks_the_hard_rules_is_rewritten_once_then_dropped():
    job = writer.Job("p1", FACTS)
    bad = GOOD.replace("42", "43")
    call, sent = fake_call([variants(bad, bad), variants(bad, bad)], [ok(0), ok(0)])
    writer.write_all([job], examples=[], call=call, log=lambda m: None)
    assert job.chosen is None and job.dropped
    assert len(sent) == 4
    rewrite = json.loads(sent[2].user)["prospectos"][0]
    assert "43" in rewrite["pedido_de_correccion"]
    assert json.loads(sent[3].user)["ultima_revision"] is True


def test_rewrite_then_pass():
    job = writer.Job("p1", FACTS)
    redo = {"decision": "reescribir", "variante_elegida": None, "problemas": ["frío"], "instrucciones": "más corto", "por_que": ""}
    call, _ = fake_call([variants(), variants()], [redo, ok(0)])
    writer.write_all([job], examples=[], call=call, log=lambda m: None)
    assert job.chosen == 0 and len(job.history) == 1


def test_discarded_by_review():
    job = writer.Job("p1", FACTS)
    no = {"decision": "descartar", "variante_elegida": None, "problemas": ["sin datos"], "instrucciones": "", "por_que": ""}
    call, _ = fake_call([variants()], [no])
    writer.write_all([job], examples=[], call=call, log=lambda m: None)
    assert job.chosen is None and "descartó" in job.dropped


def test_a_failed_call_drops_the_batch_not_the_run():
    job = writer.Job("p1", FACTS)

    def call(c):
        raise claude.ClaudeError("sin cupo")
    writer.write_all([job], examples=[], call=call, log=lambda m: None)
    assert "sin cupo" in job.dropped


# ----------------------------------------------------------------------------- claude

def test_argv_has_no_tools_unless_asked():
    c = claude.Call(system="s", user="u", schema={"type": "object"}, model="claude-opus-5-5")
    args = claude.argv(c, "claude.exe")
    assert args[args.index("--tools") + 1] == "" and "--allowedTools" not in args
    assert args[args.index("--model") + 1] == "claude-opus-5-5" and "u" not in args
    web = claude.argv(claude.Call(system="s", user="u", schema={}, model="m", tools=("WebSearch", "WebFetch")), "c")
    assert web[web.index("--tools") + 1] == "WebSearch,WebFetch" and "dontAsk" in web


def test_parse():
    assert claude.parse(json.dumps({"structured_output": {"a": 1}})) == {"a": 1}
    assert claude.parse(json.dumps({"result": "{\"a\": 2}"})) == {"a": 2}
    with pytest.raises(claude.ClaudeError):
        claude.parse(json.dumps({"is_error": True, "result": "login"}))
    with pytest.raises(claude.ClaudeError):
        claude.parse("no json")


# ----------------------------------------------------------------------------- run

def cand(region, score, phone=None, kind="agencia", sources=("mercadolibre",)):
    p = Prospect([Seller(sources[0], f"{region}{score}", [row(1)])], kind=kind, phone=phone)
    return run.Candidate(p, F.Zone("06", None, region), [], score)


def test_diversify_caps_a_region():
    ranked = [cand("amba", 10 - i) for i in range(6)] + [cand("cuyo", 1)]
    order = run.diversify(ranked, 5)
    assert [c.zone.region for c in order[:3]] == ["amba", "amba", "cuyo"]


def test_find_phones_never_searches_a_person(monkeypatch):
    person = cand("amba", 3, kind="persona")
    agency = cand("cuyo", 2)
    looked = []

    def fake_web(batch, call):
        looked.extend(p.kind for p, _ in batch.values())
        return {pid: ("5492615123456", "https://agencia.com.ar") for pid in batch}
    monkeypatch.setattr(run.lookup, "web", fake_web)
    ready, missing = run.find_phones([person, agency], 5, cache={}, call=None, dry=True)
    assert looked == ["agencia"]
    assert [c.prospect.phone_source for c in ready] == ["web"] and missing == [person]


def test_find_phones_uses_the_cache(monkeypatch):
    c = cand("amba", 3)
    monkeypatch.setattr(run.lookup, "web", lambda *a, **k: pytest.fail("no debería buscar"))
    cache = {c.prospect.key: {"phone": "5491155551234", "source": "web", "evidence": "u", "checked": "2026-11-14"}}
    ready, _ = run.find_phones([c], 1, cache=cache, call=None, dry=True)
    assert ready[0].prospect.phone == "5491155551234"


def test_hook_used_is_the_car_the_text_offers():
    from prospector import writer
    hooks = [{"listing_id": 1, "auto": "Ford Focus 2009", "precio_publicado": "$7.500.000"},
             {"listing_id": 2, "auto": "Toyota Hilux DX 2013", "precio_publicado": "US$ 16.800"}]
    text = "Anteayer salió una Toyota Hilux DX 2013 a US$ 16.800, 16 % abajo de 18 parecidas.\n\n¿Les paso el aviso?"
    assert writer.hook_used(text, hooks)["listing_id"] == 2
    assert writer.hook_used("Hay 7 búsquedas de Gol Trend cerca. ¿Te cuento?", hooks) is None
    job = writer.Job("p1", {"ganchos": hooks}, variants=[{"tipo_gancho": "oportunidad", "texto": text}], chosen=0)
    assert job.hook["auto"] == "Toyota Hilux DX 2013"


@pytest.mark.parametrize("change, reason", [
    ({}, None),
    ({"title": "Toyota Etios 2015 anticipo"}, "anticipo o cuotas"),
    ({"description": "Entrega de $3.000.000 y el resto en 12 cuotas"}, "anticipo o cuotas"),
    ({"title": "Etios 2015 -chocado-"}, "daño"),
    ({"description": "Se vende para repuestos, sin motor"}, "daño"),
    ({"description": "Nunca chocado, impecable"}, None),
    ({"images": ["solo"]}, "una sola foto"),
    ({"price": 11_900, "currency": "ARS"}, "precio que no cierra con la moneda"),
    ({"price_published": 9_000, "price_published_currency": "USD"}, "el precio publicado y el de la descripción no coinciden"),
])
def test_hook_risk(change, reason):
    from prospector import facts as F
    r = hook_row(1, description="Toyota Etios 2015 único dueño, service al día, listo para transferir", mileage_km=90_000)
    r.update(change)
    assert F.hook_risk(r, r["ref"]) == reason


def test_a_deep_discount_needs_more_proof():
    from prospector import facts as F
    r = hook_row(1, diff=28.0, n=124, description="Corsa 2007 impecable, papeles al día, listo para transferir",
                 mileage_km=150_000)
    assert F.hook_risk(r, r["ref"]) is None
    assert F.hook_risk({**r, "mileage_km": None}, r["ref"]) == "descuento de más del 25 % sin respaldo suficiente"
    assert F.hook_risk(r, {"n": 12, "diff_pct": 28.0}) == "descuento de más del 25 % sin respaldo suficiente"


def test_only_hooks_still_published_are_kept():
    from prospector import facts as F
    from prospector.alive import Check
    cands = [{"row": {"id": i}, "tier": 3, "rank": 100 - i} for i in range(4)]
    states = {0: "gone", 1: "online", 2: "unknown", 3: "online"}
    got = F.live_hooks(cands, lambda r: Check(states[r["id"]], "pagina", NOW))
    assert [c["row"]["id"] for c in got] == [1, 3]
    assert got[0]["verified"] == {"como": "pagina", "en": NOW.isoformat()}


def test_alive_reads_the_page_and_never_takes_a_failed_read_as_gone():
    from prospector.alive import Checker

    class Resp:
        def __init__(self, status, text=""):
            self.status_code, self.text, self.url = status, text, "https://x"

    seen = []
    def get(url, follow):
        seen.append(url)
        if "boom" in url:
            raise RuntimeError("timeout")
        return Resp(404)
    c = Checker(get=get, now=lambda: NOW, sleep=lambda s: None)
    assert c.check({"id": 1, "source": "mercadolibre", "url": "https://ml/1"}).state == "gone"
    assert c.check({"id": 1, "source": "mercadolibre", "url": "https://ml/1"}).state == "gone"   # cached
    assert c.check({"id": 2, "source": "mercadolibre", "url": "https://ml/boom"}).state == "unknown"
    assert len(seen) == 2
    fb = {"id": 3, "source": "facebook", "url": "https://fb/3"}
    assert c.check({**fb, "last_seen_at": NOW - timedelta(hours=3)}).state == "online"
    assert c.check({**fb, "id": 4, "last_seen_at": NOW - timedelta(hours=30)}).state == "unknown"
    assert len(seen) == 2                      # Facebook is never fetched


@pytest.mark.parametrize("kind, name, first, expected", [
    ("agencia", "Julio Quiroga Automotores", None, "Hola, Julio."),
    ("agencia", "Favale Motors", None, "Hola, ¿cómo andan?"),
    ("agencia", "ALL MOTORS", None, "Hola, ¿cómo andan?"),
    ("agencia", "Lasho Lashocito", None, "Hola, ¿cómo andan?"),
    ("persona", "Marta Gómez", "Marta", "Hola, Marta."),
    ("persona", "autos_rosario22", None, "Hola, ¿cómo estás?"),
])
def test_greeting(kind, name, first, expected):
    from prospector import facts as F
    p = Prospect([Seller("facebook", name, [row(i, name=name) for i in range(3)])], kind=kind)
    assert F.greeting(p, first) == expected


def test_rules_greeting_and_one_car_stock_fact():
    from prospector import rules
    facts = {"saludo": "Hola, ¿cómo andan?", "stock": {"avisos_activos": 14}}
    ok = "Hola, ¿cómo andan? Soy Juan, armé Ese Auto.\n\nVi que tienen 14 autos publicados. ¿Les paso uno?"
    assert rules.check(ok, facts) == []
    assert any("saludo" in p for p in rules.check(ok.replace("¿cómo andan?", "Favale Motors."), facts))
    weak = "Hola, ¿cómo andan? Soy Juan, armé Ese Auto.\n\nVi que tienen un Gol Trend. ¿Les paso uno?"
    assert any("un solo auto" in p for p in rules.check(weak, facts))


def test_merged_profiles_over_the_cap_are_left_out():
    from prospector import sellers as S
    shared = [dict(id=1000 + k, source="facebook", seller_name=None, make="Ford", model="Ranger", year=2015,
                   price=20_000_000 + k, description="") for k in range(3)]
    rows = []
    for name, base in (("Perfil Uno", 0), ("Perfil Dos", 100)):
        for k in range(3):
            rows.append({**shared[k], "id": base + k, "seller_name": name})
        for k in range(32):
            rows.append(dict(id=base + 10 + k, source="facebook", seller_name=name, make="Fiat", model=f"M{base}{k}",
                             year=2010, price=5_000_000 + base * 1000 + k, description=""))
    out, dropped = S.build_prospects(rows, contacted=S.Contacted(frozenset(), frozenset(), frozenset()))
    assert out == [] and dropped["más de 60 avisos al juntar perfiles"] == 1


def test_hooks_prefer_a_model_the_seller_has_several_of():
    rows = [row(i, name="Autos del Parque Demo", model="Etios", year=2010 + i) for i in range(3)] + \
           [row(10, name="Autos del Parque Demo", model="Corolla", year=2016)]
    p = Prospect([Seller("rosariogarage", "Autos del Parque Demo", rows)], kind="agencia")
    zone = F.zone_of(p.listings, None)
    pool = [hook_row(200, model="Corolla", diff=20), hook_row(201, model="Etios", diff=14)]
    got = F.hook_candidates(pool, p, zone, None)
    assert [c["row"]["id"] for c in got] == [201, 200]
    assert F.hook_fact(got[0], NOW, "oportunidad_1")["avisos_suyos_de_ese_modelo"] == 3


# --- ML WhatsApp button ---------------------------------------------------------------------

ML_URL = "https://auto.mercadolibre.com.ar/MLA-1234567890-demo-_JM"
_ML_HTML = (Path(__file__).parent / "fixtures" / "html" / "mercadolibre_detail.html").read_text(encoding="utf-8")
_BUTTON = '<script>{"whatsapp_available":true,"action_type":"WHATSAPP"}</script>'


def test_ml_button_page_needs_both_marks_on_a_live_page():
    assert lookup.ml_button_page(_ML_HTML + _BUTTON, ML_URL, 200)
    assert not lookup.ml_button_page(_ML_HTML, ML_URL, 200)
    assert not lookup.ml_button_page(_ML_HTML + '<script>{"whatsapp_available":false,"action_type":"WHATSAPP"}</script>', ML_URL, 200)
    assert not lookup.ml_button_page(_BUTTON, ML_URL, 404)


class _Resp:
    def __init__(self, text, status=200, url=ML_URL):
        self.text, self.status_code, self.url = text, status, url


def _ml_prospect(n=3):
    rows = [row(i, source="mercadolibre", url=f"https://auto.mercadolibre.com.ar/MLA-{i}-_JM",
                last_seen_at=NOW - timedelta(hours=i)) for i in range(n)]
    return Prospect([Seller("mercadolibre", "Autos ML Demo", rows)], kind="persona")


def test_ml_button_reads_the_freshest_two_and_returns_the_url():
    p = _ml_prospect()
    asked = []

    def get(url):
        asked.append(url)
        return _Resp(_ML_HTML + (_BUTTON if url.endswith("MLA-1-_JM") else ""))
    assert lookup.ml_button(p, get=get, sleep=lambda s: None) == "https://auto.mercadolibre.com.ar/MLA-1-_JM"
    assert asked == ["https://auto.mercadolibre.com.ar/MLA-0-_JM", "https://auto.mercadolibre.com.ar/MLA-1-_JM"]

    asked.clear()
    assert lookup.ml_button(p, get=lambda u: (asked.append(u), _Resp(_ML_HTML))[1], sleep=lambda s: None) is None
    assert len(asked) == 2


def test_find_phones_takes_the_ml_button_for_a_person(monkeypatch):
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    monkeypatch.setattr(run.lookup, "web", lambda *a, **k: pytest.fail("no debería buscar"))
    person = cand("amba", 3, kind="persona")
    ready, missing = run.find_phones([person], 1, cache={}, call=None, dry=True, ml_check=lambda p: ML_URL)
    assert ready == [person] and missing == []
    assert (person.prospect.phone, person.prospect.phone_source, person.prospect.phone_evidence) == (None, "boton_ml", ML_URL)


def test_find_phones_without_the_ml_button_path(monkeypatch):
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    person = cand("amba", 3, kind="persona")
    ready, missing = run.find_phones([person], 1, cache={}, call=None, dry=True, ml_button=False,
                                     ml_check=lambda p: pytest.fail("no debería leer ML"))
    assert ready == [] and missing == [person]


def test_find_phones_rereads_ml_after_a_recent_miss(monkeypatch):
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    c = cand("amba", 3, kind="persona")
    cache = {c.prospect.key: {"phone": None, "checked": run.today_art()}}
    ready, _ = run.find_phones([c], 1, cache=cache, call=None, dry=True, ml_check=lambda p: ML_URL)
    assert ready == [c]
    other = cand("cuyo", 2, kind="persona", sources=("facebook",))
    cache = {other.prospect.key: {"phone": None, "checked": run.today_art()}}
    ready, missing = run.find_phones([other], 1, cache=cache, call=None, dry=True,
                                     ml_check=lambda p: pytest.fail("no es de ML"))
    assert ready == [] and missing == [other]


@pytest.mark.parametrize("name, out", [
    ("Carcash3", True), ("CARCASH", True), ("Tienda oficial Car Cash", True), ("Kavak2", True),
    ("KAVAK_AR", True), ("Car One", True), ("carone3", True), ("Autos San Jorge", True), ("Randazzo Usados", True),
    ("Caronello Autos", False), ("Pecarone Automotores", False), ("Autos del Parque", False), ("Romera Hnos Usados", False),
])
def test_excluded_names_catch_nicks_and_variants(name, out):
    assert sellers.excluded_name(name) is out


def _far_zone_prospect():
    # A Tandil agency: its listings sit in Tandil.
    rows = [row(i, name="Romera Demo", make="Ford", model="Ranger", province_id="06", department="Tandil",
                lat=-37.32, lon=-59.13) for i in range(4)]
    return Prospect([Seller("mercadolibre", "Romera Demo", rows)], kind="agencia")


def test_hooks_outside_the_partido_must_be_within_60_km():
    p = _far_zone_prospect()
    zone = F.Zone("06", "Tandil", "pampeana")
    far = hook_row(901, make="Ford", model="Ranger", prov="06", dept="San Isidro")
    far.update(lat=-34.47, lon=-58.51)
    near = hook_row(902, make="Ford", model="Ranger", prov="06", dept="Rauch")
    near.update(lat=-36.97, lon=-59.13)       # about 39 km
    same = hook_row(903, make="Ford", model="Ranger", prov="06", dept="Tandil")
    same.update(lat=None, lon=None)
    got = {c["row"]["id"]: c for c in F.hook_candidates([far, near, same], p, zone, None)}
    assert set(got) == {902, 903}
    assert 35 <= got[902]["km"] <= 45 and got[903]["km"] is None


@pytest.mark.parametrize("value, text", [
    (104000, "104.000 km"), (33395, "33.395 km"), (950, "950 km"), (1_250_000, "1.250.000 km"), (89999.6, "90.000 km"), (None, None),
])
def test_km_text_is_es_ar(value, text):
    assert F.km_text(value) == text


def test_hook_fact_carries_km_texto():
    p = prospect_rosario()
    c = F.hook_candidates([hook_row(950, mileage_km=104000)], p, F.zone_for(p, None), None)[0]
    fact = F.hook_fact(c, NOW, "g1")
    assert fact["km"] == 104000 and fact["km_texto"] == "104.000 km"


def test_voseo_with_accents_is_not_tuteo():
    facts = {"saludo": "Hola, Pablo."}
    vos = "Hola, Pablo. Soy Juan, de Ese Auto. Te aviso así comprás stock antes que otro y buscás menos.\n\n¿Te lo armo?"
    assert not any("tuteo" in p for p in rules.check(vos, facts))
    tu = "Hola, Pablo. Soy Juan, de Ese Auto. Te aviso así compras stock antes que otro.\n\n¿Te lo armo?"
    assert any("tuteo" in p for p in rules.check(tu, facts))
