from __future__ import annotations
import logging
import re
from typing import Any

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
from telegram.error import BadRequest
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)


log = logging.getLogger("bot")

from config import ALLOWED_USER_IDS, SOURCES
from bot.catalog import (
    MARCAS_POPULARES, COMBUSTIBLES, TRANSMISIONES, VENDEDORES, MONEDAS,
    WIZARD_STEPS, ANIOS,
)
import db
from bot.notification_actions import handler as notification_actions
from notifications.links import Links


# Filter keys that are stored as lists (multi-select).
MULTI_KEYS = {"marcas", "modelos", "anios", "sources"}


# Conversation state — a single state, the wizard advances via a step index
WIZARD = 1


def _allowed(update: Update) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    user = update.effective_user
    return user is not None and user.id in ALLOWED_USER_IDS


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text=t, callback_data=cb) for t, cb in row] for row in rows]
    )


def _grid(items: list[str], cols: int = 3, prefix: str = "v:") -> list[list[tuple[str, str]]]:
    rows = []
    row: list[tuple[str, str]] = []
    for x in items:
        row.append((x, f"{prefix}{x}"))
        if len(row) == cols:
            rows.append(row); row = []
    if row:
        rows.append(row)
    return rows


def _toggle_grid(items: list, selected: set, cols: int = 2) -> list[list[tuple[str, str]]]:
    rows: list[list[tuple[str, str]]] = []
    row: list[tuple[str, str]] = []
    for x in items:
        mark = "✅ " if x in selected else "▫️ "
        row.append((mark + str(x), f"toggle:{x}"))
        if len(row) == cols:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([("✔️ Listo", "toggle:__done__")])
    return rows


def _filter_bits(f: dict) -> list[str]:
    bits: list[str] = []
    for k in ("marcas", "modelos", "anios", "sources"):
        v = f.get(k)
        if v:
            bits.append(f"{k}=[{', '.join(map(str, v))}]")
    if f.get("origin_lat") is not None and f.get("origin_lon") is not None and f.get("radio_km"):
        bits.append(f"radio={f['radio_km']} km desde tu ubicacion")
    for k, v in f.items():
        if k in ("marcas", "modelos", "anios", "sources", "origin_lat", "origin_lon", "radio_km"):
            continue
        if v in (None, "", [], {}):
            continue
        bits.append(f"{k}={v}")
    return bits


def _md_escape(s: str) -> str:
    """Escape legacy-Markdown specials so user values (e.g. Fiesta_Kinetic)
    don't break parsing when echoed back in a wizard prompt."""
    return re.sub(r"([_*`\[])", r"\\\1", s)


def _fmt_current(key: str, f: dict) -> str | None:
    """Human-readable current value of a single-value filter, or None."""
    if key == "user_location":
        if f.get("origin_lat") is not None and f.get("origin_lon") is not None:
            return f"{f['origin_lat']:.4f}, {f['origin_lon']:.4f}"
        return None
    v = f.get(key)
    if v in (None, "", [], {}):
        return None
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return str(v)


# ---------------- commands ----------------

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    await update.message.reply_text(
        "🚗 *AutoMotive Alerts*\n\n"
        "Comandos:\n"
        "/nuevaalerta — crear alerta paso a paso\n"
        "/editar <id> — modificar una alerta existente\n"
        "/alertas — listar alertas\n"
        "/borrar <id> — eliminar alerta\n"
        "/pausar <id> — pausar alerta\n"
        "/activar <id> — activar alerta\n"
        "/cancelar — cancelar wizard en curso",
        parse_mode="Markdown",
    )


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    rows = await db.list_alerts(user_id=update.effective_user.id)
    if not rows:
        await update.message.reply_text("No tenés alertas. Creá una con /nuevaalerta")
        return
    out = ["Tus alertas:"]
    for a in rows:
        st = "🟢" if a["active"] else "⏸"
        f = a["filters"]
        bits = _filter_bits(f)
        resumen = " · ".join(bits)
        out.append(f"{st} *#{a['id']}* — {a['name']}\n   {resumen[:400]}")
    await update.message.reply_text("\n\n".join(out))


async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("Uso: /borrar <id>")
        return
    aid = int(ctx.args[0])
    a = await db.get_alert(aid)
    if not a or a["user_id"] != update.effective_user.id:
        await update.message.reply_text("Alerta no encontrada.")
        return
    await db.delete_alert(aid)
    await update.message.reply_text(f"Alerta #{aid} eliminada.")


async def _set_active(update: Update, ctx, active: bool):
    if not _allowed(update):
        return
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text(f"Uso: /{'activar' if active else 'pausar'} <id>")
        return
    aid = int(ctx.args[0])
    a = await db.get_alert(aid)
    if not a or a["user_id"] != update.effective_user.id:
        await update.message.reply_text("Alerta no encontrada.")
        return
    await db.set_alert_active(aid, active)
    await update.message.reply_text(f"Alerta #{aid} {'activada' if active else 'pausada'}.")


async def cmd_pause(update, ctx):  return await _set_active(update, ctx, False)
async def cmd_resume(update, ctx): return await _set_active(update, ctx, True)


# ---------------- wizard ----------------

async def cmd_new_alert(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return ConversationHandler.END
    ctx.user_data["wizard"] = {
        "step": 0,
        "filters": {"sources": list(SOURCES)},  # default: all sources
    }
    await update.message.reply_text(
        "🆕 *Nueva alerta*\n"
        "Cada aviso nuevo recibe un Opportunity Score de 0 a 100: precio contra "
        "publicaciones comparables, km, versión, antigüedad y datos informados. "
        "Te aviso cuando aparece una 🔥 alta oportunidad.\n\n"
        "Voy a pedirte los filtros uno por uno. En cada paso podés:\n"
        "• tocar un botón sugerido\n"
        "• escribir tu propio valor\n"
        "• mandar */skip* para saltar el filtro\n"
        "• mandar */cancelar* para abortar",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return await _ask_step(update, ctx)


async def cmd_edit_alert(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return ConversationHandler.END
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("Uso: /editar <id>  (los ids salen con /alertas)")
        return ConversationHandler.END
    aid = int(ctx.args[0])
    a = await db.get_alert(aid)
    if not a or a["user_id"] != update.effective_user.id:
        await update.message.reply_text("Alerta no encontrada.")
        return ConversationHandler.END
    filters = dict(a["filters"])
    filters.setdefault("sources", list(SOURCES))
    ctx.user_data["wizard"] = {
        "step": 0,
        "filters": filters,
        "edit_id": aid,
    }
    await update.message.reply_text(
        f"✏️ *Editando alerta #{aid}* — {a['name']}\n\n"
        "Te muestro cada filtro con su valor actual. En cada paso:\n"
        "• mandá */skip* para *mantener* el valor actual\n"
        "• escribí o tocá un botón para cambiarlo\n"
        "• */cancelar* aborta sin guardar",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return await _ask_step(update, ctx)


def _step_keyboard(key: str, current_filters: dict) -> InlineKeyboardMarkup | None:
    if key == "marcas":
        selected = set(current_filters.get("marcas", []))
        return _kb(_toggle_grid(MARCAS_POPULARES, selected, cols=3))
    if key == "anios":
        selected = set(current_filters.get("anios", []))
        return _kb(_toggle_grid(ANIOS, selected, cols=4))
    if key == "combustible":
        return _kb(_grid(COMBUSTIBLES, cols=3))
    if key == "transmision":
        return _kb(_grid(TRANSMISIONES, cols=2))
    if key == "vendedor":
        return _kb(_grid(VENDEDORES, cols=2))
    if key == "moneda":
        return _kb(_grid(MONEDAS, cols=2))
    if key == "sources":
        selected = set(current_filters.get("sources", []))
        return _kb(_toggle_grid(SOURCES, selected, cols=2))
    return None


async def _ask_step(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    w = ctx.user_data["wizard"]
    if w["step"] >= len(WIZARD_STEPS):
        return await _finish(update, ctx)

    key, label = WIZARD_STEPS[w["step"]]
    f = w["filters"]
    editing = w.get("edit_id") is not None
    cur = _fmt_current(key, f)
    keep_note = "\n_Mandá /skip para mantener el valor actual._" if (editing and cur) else ""
    target = update.callback_query.message if update.callback_query else update.message
    if key == "user_location":
        actual = f"\n\n_Actual: {_md_escape(cur)}_" if (editing and cur) else ""
        await target.reply_text(
            f"*Paso {w['step']+1}/{len(WIZARD_STEPS)}* - {label}{actual}\n\n"
            "Toca el boton *Enviar ubicacion* para usar tu ubicacion de Telegram."
            + ("\n_O mandá /skip para mantener la ubicacion actual._" if (editing and cur) else ""),
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("Enviar ubicacion", request_location=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return WIZARD
    if key == "radio_km":
        actual = f"\n\n_Actual: {_md_escape(cur)} km_" if (editing and cur) else ""
        await target.reply_text(
            f"*Paso {w['step']+1}/{len(WIZARD_STEPS)}* - {label}{actual}\n\n"
            "Mandame el radio en kilometros. Ej: `50` o `75 km`." + keep_note,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return WIZARD
    hint = ""
    if key.startswith("anio"):
        hint = "  (ej: 2018)"
    elif key.startswith("km"):
        hint = "  (ej: 80000)"
    elif key.startswith("precio"):
        hint = "  (ej: 15000 — sin puntos ni símbolo)"
    elif key == "version":
        hint = "  (ej: 1.6 GLP, Style, etc.)"
    elif key == "modelo":
        hint = f"  (ej: Gol Trend, Corolla XEi)"

    msg = f"*Paso {w['step']+1}/{len(WIZARD_STEPS)}* — {label}{hint}"
    if editing and cur:
        msg += f"\n_Actual: {_md_escape(cur)}_"
    kb = _step_keyboard(key, f)
    if kb and key in MULTI_KEYS:
        tail = (
            "\n\nLos ✅ son tu selección actual. Tocá para cambiar, o tocá *Listo* para mantenerla."
            if editing else
            "\n\nTocá los que quieras (toggle), o escribí texto libre. Tocá *Listo* para continuar."
        )
        await target.reply_text(msg + tail, parse_mode="Markdown", reply_markup=kb)
    elif kb:
        await target.reply_text(msg + keep_note, parse_mode="Markdown", reply_markup=kb)
    else:
        tail = "\n\nMandá el valor por chat, o /skip para " + ("mantener el actual." if (editing and cur) else "saltar.")
        await target.reply_text(msg + tail, parse_mode="Markdown")
    return WIZARD


def _coerce(key: str, value: str) -> Any:
    if key in ("km_min", "km_max"):
        return int("".join(ch for ch in value if ch.isdigit()))
    if key == "radio_km":
        m = re.search(r"\d+(?:[\.,]\d+)?", value)
        if not m:
            raise ValueError("radio_km missing")
        radius = float(m.group(0).replace(",", "."))
        if radius <= 0:
            raise ValueError("radio_km must be positive")
        return radius
    if key in ("precio_min", "precio_max", "precio_max_oportunidad"):
        clean = "".join(ch for ch in value if ch.isdigit())
        if not clean:
            raise ValueError(f"{key} missing")
        return float(clean)
    return value.strip()


def _split_csv(text: str) -> list[str]:
    """Split a comma-or-newline separated string into a deduped list."""
    out, seen = [], set()
    for piece in re.split(r"[,\n;]+", text):
        p = piece.strip()
        if p and p.lower() not in seen:
            out.append(p)
            seen.add(p.lower())
    return out


def _split_years(text: str) -> list[int]:
    """Parse a comma-separated list of years, optionally with ranges 'X-Y'."""
    out: set[int] = set()
    for piece in re.split(r"[,\n;]+", text):
        p = piece.strip()
        if not p:
            continue
        # range "2018-2022" → expand
        if m := re.match(r"^\s*(\d{4})\s*-\s*(\d{4})\s*$", p):
            lo, hi = int(m.group(1)), int(m.group(2))
            for y in range(min(lo, hi), max(lo, hi) + 1):
                out.add(y)
        elif p.isdigit() and 1980 <= int(p) <= 2030:
            out.add(int(p))
    return sorted(out)


async def wizard_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    w = ctx.user_data.get("wizard")
    if not w:
        return ConversationHandler.END
    key, _ = WIZARD_STEPS[w["step"]]
    if key != "user_location":
        await update.message.reply_text("Ahora no estoy esperando una ubicacion.")
        return WIZARD
    loc = update.message.location
    if not loc:
        await update.message.reply_text("No pude leer la ubicacion. Usa el boton de Telegram.")
        return WIZARD

    w["filters"]["origin_lat"] = float(loc.latitude)
    w["filters"]["origin_lon"] = float(loc.longitude)
    w["step"] += 1
    return await _ask_step(update, ctx)


async def wizard_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    w = ctx.user_data.get("wizard")
    if not w:
        return ConversationHandler.END
    txt = (update.message.text or "").strip()
    key, _ = WIZARD_STEPS[w["step"]]
    if txt.lower() in ("/skip", "skip", "-"):
        if key in ("user_location", "radio_km"):
            # Distance filtering needs both. New alerts must supply them; when
            # editing, /skip keeps whatever the alert already had.
            has_value = (
                (w["filters"].get("origin_lat") is not None
                 and w["filters"].get("origin_lon") is not None)
                if key == "user_location"
                else bool(w["filters"].get("radio_km"))
            )
            if not (w.get("edit_id") is not None and has_value):
                await update.message.reply_text("Este paso es necesario para filtrar por distancia.")
                return WIZARD
        w["step"] += 1
        return await _ask_step(update, ctx)

    if key == "user_location":
        await update.message.reply_text("Usa el boton *Enviar ubicacion* de Telegram.", parse_mode="Markdown")
        return WIZARD
    if key == "sources":
        await update.message.reply_text("Para plataformas usá los botones de arriba 👆")
        return WIZARD
    try:
        # Multi-value steps accept text input as additive set:
        # marcas/modelos accept comma-separated names; anios accept years/ranges
        if key == "marcas":
            existing = set(w["filters"].get("marcas", []))
            existing.update(_split_csv(txt))
            w["filters"]["marcas"] = sorted(existing)
            await update.message.reply_text(
                f"Marcas actuales: {', '.join(w['filters']['marcas']) or '(ninguna)'}\n"
                "Seguí tocando botones, escribí más, o tocá ✔️ Listo arriba para continuar."
            )
            return WIZARD
        if key == "modelos":
            existing = set(w["filters"].get("modelos", []))
            existing.update(_split_csv(txt))
            w["filters"]["modelos"] = sorted(existing)
            # modelos has no inline keyboard, so accept and advance
            w["step"] += 1
            return await _ask_step(update, ctx)
        if key == "anios":
            existing = set(w["filters"].get("anios", []))
            existing.update(_split_years(txt))
            w["filters"]["anios"] = sorted(existing)
            await update.message.reply_text(
                f"Años actuales: {', '.join(map(str, w['filters']['anios'])) or '(ninguno)'}\n"
                "Seguí tocando, escribí más (ej: 2018-2022), o tocá ✔️ Listo."
            )
            return WIZARD
        w["filters"][key] = _coerce(key, txt)
    except ValueError:
        await update.message.reply_text("No pude leer ese valor, probá de nuevo o /skip.")
        return WIZARD
    w["step"] += 1
    return await _ask_step(update, ctx)


async def wizard_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    w = ctx.user_data.get("wizard")
    if not w:
        await q.answer("Wizard no activo. Mandá /nuevaalerta para empezar.", show_alert=True)
        return ConversationHandler.END

    data = q.data or ""
    key, _ = WIZARD_STEPS[w["step"]]
    log.info("wizard_callback: step=%s key=%s data=%s", w["step"], key, data)

    if data.startswith("toggle:"):
        val = data.split(":", 1)[1]
        # Stale buttons from a prior step: ignore but acknowledge so the
        # client doesn't keep showing the loading spinner.
        if key not in MULTI_KEYS:
            await q.answer("Botón viejo — usá los del paso actual", show_alert=False)
            return WIZARD

        sel = set(w["filters"].get(key, []))
        if val == "__done__":
            w["filters"][key] = sorted(sel)
            w["step"] += 1
            await q.answer(f"✔️ {len(sel)} seleccionado(s)")
            return await _ask_step(update, ctx)

        # Year toggles arrive as strings; coerce back to int for `anios`.
        coerced: Any = int(val) if key == "anios" and val.isdigit() else val
        if coerced in sel:
            sel.discard(coerced)
            await q.answer(f"➖ {coerced}")
        else:
            sel.add(coerced)
            await q.answer(f"✅ {coerced}")
        w["filters"][key] = sorted(sel, key=str)

        kb = _step_keyboard(key, w["filters"])
        try:
            await q.edit_message_reply_markup(reply_markup=kb)
        except BadRequest as e:
            # "Message is not modified" is harmless; anything else is a real bug.
            if "not modified" not in str(e).lower():
                log.warning("edit_message_reply_markup failed: %s", e)
        except Exception:
            log.exception("toggle render failed")
        return WIZARD

    if data.startswith("v:"):
        raw = data.split(":", 1)[1]
        try:
            w["filters"][key] = _coerce(key, raw)
        except ValueError:
            await q.answer("Valor inválido", show_alert=True)
            return WIZARD
        await q.answer(f"✓ {raw}")
        w["step"] += 1
        return await _ask_step(update, ctx)

    await q.answer()
    return WIZARD


async def _finish(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    w = ctx.user_data.pop("wizard")
    f = w["filters"]
    marcas = f.get("marcas") or []
    modelos = f.get("modelos") or []
    name = (
        f"{'/'.join(marcas[:3])} {'/'.join(modelos[:3])}".strip()
        or "Alerta"
    )
    target = update.callback_query.message if update.callback_query else update.message
    resumen = "\n".join(f"- {bit}" for bit in _filter_bits(f))
    edit_id = w.get("edit_id")
    if edit_id is not None:
        # Extra marcas/modelos added while editing become new alerts.
        new_ids = await db.update_alert(edit_id, name, f)
        extra = (f"\nNuevas alertas por modelo: {', '.join(f'#{i}' for i in new_ids)}"
                 if new_ids else "")
        await target.reply_text(
            f"Alerta #{edit_id} actualizada - {name}{extra}\n\n{resumen}\n\n"
            f"Los cambios se aplican en el próximo chequeo. "
            f"Mantengo el historial de avisos ya vistos.",
        )
        return ConversationHandler.END
    # One alert per (marca, modelo): several models become several alerts.
    ids = await db.create_alert(
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        name=name,
        filters=f,
    )
    creadas = (f"Alerta #{ids[0]} creada" if len(ids) == 1
               else f"Alertas {', '.join(f'#{i}' for i in ids)} creadas (una por modelo)")
    await target.reply_text(
        f"{creadas} - {name}\n\n{resumen}\n\n"
        f"Voy a notificarte cuando aparezcan oportunidades.",
    )
    return ConversationHandler.END


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("wizard", None)
    await update.message.reply_text("Cancelado.")
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("nuevaalerta", cmd_new_alert),
            CommandHandler("editar", cmd_edit_alert),
        ],
        states={
            WIZARD: [
                CallbackQueryHandler(wizard_callback),
                MessageHandler(filters.LOCATION, wizard_location),
                MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_text),
                CommandHandler("skip", wizard_text),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cmd_cancel)],
        per_user=True,
        per_chat=True,
    )


def register(app, links: Links | None = None):
    # Before the wizard: its CallbackQueryHandler takes any callback while a
    # conversation is open.
    app.add_handler(notification_actions(links or Links()))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("alertas", cmd_list))
    app.add_handler(CommandHandler("borrar", cmd_delete))
    app.add_handler(CommandHandler("pausar", cmd_pause))
    app.add_handler(CommandHandler("activar", cmd_resume))
    app.add_handler(build_conversation())
