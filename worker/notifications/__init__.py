"""Notification engine (sección 7): decide → queue → channels, plus the daily digest.

    engine.py     the decision table (pure)
    service.py    listing/match events → notifications rows
    dispatch.py   queued rows → channels, with retries
    digest.py     the daily summary
    templates.py  §22 copy for Telegram, email and web
    links.py      /r/<id> tracked links
    channels/     Channel adapters: telegram, email (Resend), web
"""
