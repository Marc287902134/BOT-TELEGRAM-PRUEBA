import json, logging, asyncio, re
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from .config import settings
from . import db
from .agent import Agent
from .hubspot import HubSpot

log = logging.getLogger(__name__)

def authorized(user_id):
    return user_id in settings.allowed_user_ids

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update.effective_user.id):
        await update.message.reply_text("No estás autorizado para utilizar este asistente.")
        return
    await update.message.reply_text(
        "¡Conectado! Soy vuestro asistente de HubSpot. Escríbeme en lenguaje natural.\n\n"
        "Ejemplos: «Busca los negocios abiertos», «Crea un contacto…», "
        "«Pon una tarea para llamar a Ana mañana a las 10».\n"
        "/ayuda para ver ejemplos."
    )

async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Tu ID numérico de Telegram es: {update.effective_user.id}")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update.effective_user.id): return
    await update.message.reply_text(
        "Puedo consultar y gestionar contactos, empresas, negocios, tareas, tickets, "
        "reuniones y notas. También puedo consultar pipelines y propiedades.\n\n"
        "Para cambios delicados te pediré confirmación. Usa /cancelar para cancelar "
        "una confirmación pendiente."
    )

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if not authorized(user):
        await update.message.reply_text("No estás autorizado.")
        return
    agent: Agent = context.application.bot_data["agent"]
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        answer = await agent.chat(user, update.message.text)
        marker = None
        if "CONFIRM_IDS:" in answer:
            answer, marker = answer.split("CONFIRM_IDS:", 1)
            pids = [x.strip() for x in marker.strip().split(",") if x.strip()]
            rows = [[InlineKeyboardButton(f"Confirmar {pid}", callback_data=f"approve:{pid}"),
                     InlineKeyboardButton(f"Cancelar {pid}", callback_data=f"reject:{pid}")]
                    for pid in pids[:4]]
            kb = InlineKeyboardMarkup(rows)
            await update.message.reply_text(answer.strip(), reply_markup=kb)
        else:
            await update.message.reply_text(answer)
    except Exception:
        log.exception("Error procesando mensaje")
        await update.message.reply_text("He encontrado un error al procesar la petición. Revisa los logs o prueba a formularla de otra manera.")

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user.id
    if not authorized(user): return
    action, pid = q.data.split(":",1)
    pending = db.get_pending(pid,user)
    if not pending:
        await q.edit_message_text("Esta confirmación ya no existe o ha caducado.")
        return
    if action == "reject":
        db.delete_pending(pid)
        await q.edit_message_text("Operación cancelada. No he modificado HubSpot.")
        return
    agent: Agent = context.application.bot_data["agent"]
    try:
        result = await agent.execute(user,pending)
        db.audit(user,pending.get("operation"),pending)
        db.delete_pending(pid)
        await q.edit_message_text("Operación ejecutada y confirmada por HubSpot:\n" +
                                  json.dumps(result,ensure_ascii=False,default=str)[:3000])
    except Exception as e:
        await q.edit_message_text(f"No se ha podido ejecutar la operación: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update.effective_user.id): return
    await update.message.reply_text("Para cancelar una acción pendiente, pulsa «Cancelar» en su mensaje de confirmación.")

async def notifications(app: Application):
    hs: HubSpot = app.bot_data["hubspot"]
    tz = ZoneInfo(settings.timezone)
    while True:
        try:
            now = datetime.now(tz)
            # Notificaciones de cambios recientes. Se inicializa el cursor en el primer ciclo.
            for event_key, label, obj in [("contacts","contactos","contacts"),("companies","empresas","companies"),("deals","negocios","deals"),("tickets","tickets","tickets"),("tasks","tareas","tasks")]:
                if event_key not in settings.events: continue
                cursor = db.get_event_state(obj)
                if not cursor:
                    db.set_event_state(obj, str(int((now-timedelta(minutes=30)).timestamp()*1000)))
                    continue
                data = await hs.recent(obj, cursor)
                results = data.get("results",[])
                for item in reversed(results):
                    props = item.get("properties",{})
                    stamp = props.get("hs_lastmodifieddate") or props.get("createdate")
                    if stamp:
                        db.set_event_state(obj, str(max(int(cursor),int(stamp))))
                    # Para no saturar Telegram, notificar solo los 5 más recientes por ciclo.
                    for uid in settings.allowed_user_ids:
                        await app.bot.send_message(uid, f"Actualización en HubSpot · {label}\n"
                            f"ID: {item.get('id')}\n"
                            f"{json.dumps(props,ensure_ascii=False)[:1200]}")
            await asyncio.sleep(max(60,settings.poll_interval))
        except Exception:
            log.exception("Error en el sondeo de notificaciones")
            await asyncio.sleep(60)

async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    agent: Agent = context.application.bot_data["agent"]
    for uid in settings.allowed_user_ids:
        try:
            answer = await agent.chat(uid, "Prepara un resumen de mis tareas pendientes y actividad reciente del CRM.")
            await context.bot.send_message(uid, "Resumen diario de HubSpot\n\n"+answer[:3500])
        except Exception:
            log.exception("No se pudo enviar el resumen diario")

async def post_init(app: Application):
    import asyncio
    hs = HubSpot()
    agent = Agent(hs)
    app.bot_data["hubspot"] = hs
    app.bot_data["agent"] = agent
    app.create_task(notifications(app))
    try:
        hh, mm = map(int, settings.daily_summary_time.split(":"))
        app.job_queue.run_daily(daily_summary, time=time(hh,mm,tzinfo=ZoneInfo(settings.timezone)))
    except Exception:
        log.warning("Resumen diario desactivado: DAILY_SUMMARY_TIME debe tener formato HH:MM")

async def post_shutdown(app: Application):
    hs = app.bot_data.get("hubspot")
    if hs: await hs.close()

def build_app():
    app = Application.builder().token(settings.telegram_token).post_init(post_init).post_shutdown(post_shutdown).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("ayuda",help_cmd))
    app.add_handler(CommandHandler("whoami",whoami))
    app.add_handler(CommandHandler("cancelar",cancel))
    app.add_handler(CallbackQueryHandler(on_callback, pattern=r"^(approve|reject):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,on_text))
    return app
