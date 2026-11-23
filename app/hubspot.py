import httpx
from datetime import datetime, timezone, timedelta
from .config import settings

OBJECTS = {
    "contactos": "contacts", "contacto": "contacts", "contacts": "contacts",
    "empresas": "companies", "empresa": "companies", "companies": "companies",
    "negocios": "deals", "negocio": "deals", "deals": "deals",
    "tickets": "tickets", "ticket": "tickets",
    "tareas": "tasks", "tarea": "tasks", "tasks": "tasks",
    "reuniones": "meetings", "reunion": "meetings", "meetings": "meetings",
    "notas": "notes", "nota": "notes", "notes": "notes",
}
READ_ONLY_SPECIAL = {"meetings", "notes"}

class HubSpot:
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=settings.hubspot_base,
            headers={"Authorization": f"Bearer {settings.hubspot_token}",
                     "Content-Type": "application/json"},
            timeout=30
        )

    async def close(self):
        await self.client.aclose()

    async def request(self, method, path, **kwargs):
        r = await self.client.request(method, path, **kwargs)
        if r.is_error:
            try: detail = r.json()
            except Exception: detail = r.text[:1000]
            raise RuntimeError(f"HubSpot API ({r.status_code}): {detail}")
        return r.json() if r.content else {}

    @staticmethod
    def normalize_object(obj):
        key = obj.lower().strip()
        if key not in OBJECTS:
            raise ValueError("Tipo de registro no soportado. Usa contactos, empresas, negocios, tickets, tareas, reuniones o notas.")
        return OBJECTS[key]

    async def search(self, obj, query="", properties=None, limit=10):
        obj = self.normalize_object(obj)
        props = properties or self.default_properties(obj)
        body = {"filterGroups": [], "properties": props, "limit": min(max(limit,1),50),
                "sorts": [{"propertyName":"createdate","direction":"DESCENDING"}]}
        if query:
            # Búsqueda textual nativa de HubSpot sobre campos indexados.
            body["query"] = query
        return await self.request("POST", f"/crm/v3/objects/{obj}/search", json=body)

    def default_properties(self, obj):
        return {
            "contacts": ["hs_lastmodifieddate","createdate","firstname","lastname","email","phone","company","jobtitle","lifecyclestage"],
            "companies": ["hs_lastmodifieddate","createdate","name","domain","phone","city","industry"],
            "deals": ["hs_lastmodifieddate","createdate","dealname","amount","dealstage","pipeline","closedate","description"],
            "tickets": ["hs_lastmodifieddate","createdate","subject","content","hs_pipeline","hs_pipeline_stage","hs_ticket_priority"],
            "tasks": ["hs_lastmodifieddate","createdate","hs_task_subject","hs_task_body","hs_task_status","hs_task_priority","hs_timestamp","hubspot_owner_id"],
            "meetings": ["hs_meeting_title","hs_meeting_start_time","hs_meeting_end_time","hs_meeting_body"],
            "notes": ["hs_note_body","hs_timestamp"],
        }.get(obj, [])

    async def get(self, obj, record_id):
        obj = self.normalize_object(obj)
        return await self.request("GET", f"/crm/v3/objects/{obj}/{record_id}",
                                  params={"properties": ",".join(self.default_properties(obj)),
                                          "associations": "contacts,companies,deals,tickets"})

    async def create(self, obj, properties, associations=None):
        obj = self.normalize_object(obj)
        body = {"properties": properties}
        if associations:
            body["associations"] = associations
        return await self.request("POST", f"/crm/v3/objects/{obj}", json=body)

    async def update(self, obj, record_id, properties):
        obj = self.normalize_object(obj)
        return await self.request("PATCH", f"/crm/v3/objects/{obj}/{record_id}",
                                  json={"properties": properties})

    async def delete(self, obj, record_id):
        obj = self.normalize_object(obj)
        await self.request("DELETE", f"/crm/v3/objects/{obj}/{record_id}")
        return {"id": record_id, "deleted": True}

    async def associate(self, from_obj, from_id, to_obj, to_id, association_type_id=1):
        a, b = self.normalize_object(from_obj), self.normalize_object(to_obj)
        return await self.request("PUT", f"/crm/v4/objects/{a}/{from_id}/associations/{b}/{to_id}",
                                  json=[{"associationCategory":"HUBSPOT_DEFINED",
                                         "associationTypeId": int(association_type_id)}])

    async def pipelines(self, obj="deals"):
        obj = self.normalize_object(obj)
        return await self.request("GET", f"/crm/v3/pipelines/{obj}")

    async def properties_schema(self, obj):
        obj = self.normalize_object(obj)
        return await self.request("GET", f"/crm/v3/properties/{obj}")

    async def recent(self, obj, after):
        obj = self.normalize_object(obj)
        props = self.default_properties(obj)
        body = {"filterGroups":[{"filters":[{"propertyName":"hs_lastmodifieddate",
                    "operator":"GTE","value":str(after)}]}],
                "properties":props,"limit":50,
                "sorts":[{"propertyName":"hs_lastmodifieddate","direction":"DESCENDING"}]}
        return await self.request("POST", f"/crm/v3/objects/{obj}/search", json=body)
