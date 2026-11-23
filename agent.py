import json, uuid
from openai import AsyncOpenAI
from .config import settings
from . import db

SYSTEM = '''
Eres el asistente de CRM de la empresa. Hablas siempre en español, eres claro y conciso.
Tu trabajo es interpretar instrucciones y operar HubSpot usando exclusivamente la herramienta hubspot_action.
No inventes resultados ni IDs. Antes de crear, busca posibles duplicados si hay email, dominio o nombre.
Si faltan datos imprescindibles, pregunta solo por el dato que falta.
Usa fechas ISO 8601. La zona horaria del usuario es Europe/Madrid.
Para tareas, usa propiedades HubSpot: hs_task_subject, hs_task_body, hs_task_status,
hs_task_priority, hs_timestamp y hubspot_owner_id. Para contactos usa firstname, lastname,
email, phone, company, jobtitle. Para empresas usa name, domain, phone, city, industry.
Para negocios usa dealname, amount, dealstage, pipeline, closedate, description.
Para tickets usa subject, content, hs_pipeline, hs_pipeline_stage, hs_ticket_priority.
Para notas usa hs_note_body y hs_timestamp. Para reuniones usa hs_meeting_title,
hs_meeting_start_time, hs_meeting_end_time, hs_meeting_body.
Si el usuario dice "mañana", "el viernes", etc., calcula fecha local solo si el contexto
incluye fecha actual; si no, pregunta o utiliza la fecha actual del sistema.
Nunca digas que algo se ha guardado hasta que la herramienta confirme éxito.
'''

TOOL = [{
 "type":"function",
 "function":{
  "name":"hubspot_action",
  "description":"Consulta o modifica objetos del CRM HubSpot. Devuelve datos reales.",
  "parameters":{
   "type":"object","properties":{
    "operation":{"type":"string","enum":["search","get","create","update","delete","associate","pipelines","properties"]},
    "object":{"type":"string","enum":["contactos","empresas","negocios","tickets","tareas","reuniones","notas"]},
    "record_id":{"type":"string"},
    "query":{"type":"string"},
    "properties":{"type":"object","additionalProperties":{"type":["string","number","boolean","null"]}},
    "target_object":{"type":"string","enum":["contactos","empresas","negocios","tickets","tareas","reuniones","notas"]},
    "target_id":{"type":"string"},
    "limit":{"type":"integer"}
   },
   "required":["operation","object"]
  }
 }
}]

class Agent:
    def __init__(self, hubspot):
        self.hs = hubspot
        self.client = AsyncOpenAI(api_key=settings.ai_key, base_url=settings.ai_base)

    async def execute(self, user_id, args):
        op, obj = args["operation"], args["object"]
        if op == "search":
            return await self.hs.search(obj, args.get("query",""), limit=args.get("limit",10))
        if op == "get":
            if not args.get("record_id"): raise ValueError("Falta record_id.")
            return await self.hs.get(obj, args["record_id"])
        if op == "create":
            props = args.get("properties") or {}
            if not props: raise ValueError("No se han indicado propiedades para crear el registro.")
            # Chequeo básico de duplicados por email para contactos.
            if obj in ("contactos",) and props.get("email"):
                existing = await self.hs.search(obj, props["email"], limit=5)
                if existing.get("results"):
                    return {"possible_duplicates": existing["results"],
                            "message":"He encontrado posibles contactos existentes. No he creado nada."}
            return await self.hs.create(obj, props)
        if op == "update":
            if not args.get("record_id"): raise ValueError("Falta record_id.")
            props = args.get("properties") or {}
            if not props: raise ValueError("No se han indicado cambios.")
            return await self.hs.update(obj, args["record_id"], props)
        if op == "delete":
            if not args.get("record_id"): raise ValueError("Falta record_id.")
            return await self.hs.delete(obj, args["record_id"])
        if op == "associate":
            if not all(args.get(k) for k in ("record_id","target_object","target_id")):
                raise ValueError("Para asociar necesito los dos IDs y los dos tipos de objeto.")
            return await self.hs.associate(obj,args["record_id"],args["target_object"],args["target_id"])
        if op == "pipelines":
            return await self.hs.pipelines(obj)
        if op == "properties":
            return await self.hs.properties_schema(obj)
        raise ValueError("Operación no reconocida.")

    def requires_confirmation(self, args):
        if args["operation"] == "delete" and settings.confirm_deletes:
            return True
        if args["object"] == "negocios" and args["operation"] == "update" and settings.confirm_deal_stage_changes:
            return bool((args.get("properties") or {}).get("dealstage"))
        if args["object"] == "negocios" and args["operation"] == "update":
            return bool((args.get("properties") or {}).get("closedate"))
        return False

    async def chat(self, user_id, text):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        local_now = datetime.now(ZoneInfo(settings.timezone)).strftime("%A %d-%m-%Y %H:%M")
        history = db.get_memory(user_id)
        messages = [{"role":"system","content":SYSTEM + f"\nFecha y hora local actual: {local_now}."}] + history + [{"role":"user","content":text}]
        pending_ids = []
        for _ in range(5):
            response = await self.client.chat.completions.create(
                model=settings.ai_model, messages=messages, tools=TOOL,
                tool_choice="auto", temperature=0.1
            )
            msg = response.choices[0].message
            if not msg.tool_calls:
                answer = msg.content or "No he podido generar una respuesta."
                if pending_ids:
                    answer += "\n\nCONFIRM_IDS:" + ",".join(pending_ids)
                db.save_memory(user_id, messages[1:] + [{"role":"assistant","content":answer}])
                return answer
            messages.append(msg.model_dump(exclude_none=True))
            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                if self.requires_confirmation(args):
                    pid = uuid.uuid4().hex[:8]
                    db.save_pending(pid,user_id,args)
                    pending_ids.append(pid)
                    result = {"confirmation_required":True,"id":pid,"action":args,
                              "message":"La acción está pendiente de aprobación del usuario."}
                else:
                    try:
                        result = await self.execute(user_id,args)
                        db.audit(user_id, args.get("operation"), args)
                    except Exception as e:
                        result = {"error":str(e)}
                messages.append({"role":"tool","tool_call_id":call.id,
                                 "content":json.dumps(result,ensure_ascii=False,default=str)[:12000]})
        response = await self.client.chat.completions.create(
            model=settings.ai_model, messages=messages, temperature=0.1
        )
        answer = response.choices[0].message.content or "Operación procesada."
        if pending_ids:
            answer += "\n\nCONFIRM_IDS:" + ",".join(pending_ids)
        db.save_memory(user_id, messages[1:] + [{"role":"assistant","content":answer}])
        return answer
