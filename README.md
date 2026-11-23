# Agente Telegram + HubSpot

Asistente de Telegram en español para consultar y gestionar HubSpot mediante lenguaje natural. Diseñado para dos usuarios autorizados y despliegue en Railway.

## Qué incluye esta primera versión

- Bot de Telegram con lista blanca por ID numérico de usuario.
- Conexión a HubSpot mediante Private App token.
- IA compatible con API OpenAI (Groq por defecto) y llamadas a herramientas.
- Consultas y operaciones CRUD para contactos, empresas, negocios, tickets, tareas, reuniones y notas.
- Lectura de pipelines y propiedades del CRM.
- Memoria conversacional básica por usuario en SQLite.
- Confirmación obligatoria para borrados y cambios de etapa/cierre de negocios.
- Registro de auditoría local.
- Sondeo de cambios y resumen diario programado y notificaciones por sondeo de cambios recientes.
- Persistencia en SQLite; en Railway debe usarse un Volume montado en `/data`.

> Importante: esta es una base funcional inicial que requiere pruebas con un portal HubSpot de prueba antes de darle acceso al CRM real. Las propiedades requeridas y los IDs de asociación varían según la configuración del portal. La API de HubSpot también puede exigir scopes adicionales para reuniones, notas, tareas y tickets.

## Requisitos

- Python 3.12+
- Bot creado con @BotFather.
- HubSpot Private App con scopes apropiados.
- API key del proveedor de IA.

## Configuración local

1. Copia `.env.example` a `.env`.
2. Completa las variables.
3. Instala dependencias:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
   pip install -r requirements.txt
   ```
4. Arranca:

   ```bash
   python -m app.main
   ```

## Obtener los IDs de Telegram

Añade temporalmente tu bot a un chat privado y envía `/start`. Envía `/whoami` al bot: te devolverá tu ID numérico de usuario. Repite con tu socio y añade ambos IDs a `TELEGRAM_ALLOWED_USER_IDS`, separados por coma. No uses el ID del chat como sustituto del ID de usuario.

## Scopes de HubSpot

En la Private App, empieza por conceder los scopes de lectura y escritura necesarios para los objetos utilizados. Como mínimo revisa:

- `crm.objects.contacts.read` y `crm.objects.contacts.write`
- `crm.objects.companies.read` y `crm.objects.companies.write`
- `crm.objects.deals.read` y `crm.objects.deals.write`
- `crm.objects.tickets.read` y `crm.objects.tickets.write`
- `crm.objects.tasks.read` y `crm.objects.tasks.write`
- `crm.objects.notes.read` y `crm.objects.notes.write`
- `crm.objects.meetings.read` y `crm.objects.meetings.write`
- `crm.schemas.*.read` para descubrir propiedades y pipelines
- scopes de asociaciones que correspondan a los objetos utilizados

Los nombres/alcance exactos disponibles dependen del producto HubSpot y de la cuenta. Concede solo los permisos necesarios. Si HubSpot devuelve `403`, revisa el scope indicado en el error.

## Railway

1. Sube este proyecto a un repositorio privado de GitHub.
2. En Railway crea un proyecto y despliega desde GitHub.
3. Añade las variables de `.env.example` en Variables.
4. Añade un Volume y móntalo en `/data`.
5. Configura `DATABASE_PATH=/data/agent.db`.
6. Mantén una sola réplica para evitar que dos procesos consuman las actualizaciones del mismo bot.

El plan Free de Railway tiene límites de recursos y puede detener servicios al agotarse el crédito. Para un bot disponible 24/7, comprueba el coste del plan Hobby antes de producción.

## Seguridad imprescindible

- No subas `.env` a GitHub.
- No pegues tokens en chats ni tickets.
- Si un token ya se ha compartido, revócalo y genera otro.
- Restringe el bot a los dos IDs de Telegram autorizados.
- Empieza con un portal de pruebas o con operaciones de solo lectura.
- Revisa los permisos de la Private App y los registros de auditoría.
- Haz una copia del volumen SQLite.
- No habilites borrados en producción hasta validar el flujo de confirmación.

## Limitaciones conocidas de esta primera entrega

- La asociación avanzada utiliza el tipo de asociación estándar `1`; en HubSpot puede ser distinto según el par de objetos. Debe consultarse el endpoint de etiquetas de asociación y configurarse para el portal.
- La detección de duplicados automática está implementada para contactos por email; conviene ampliarla a empresas por dominio y a otros criterios.
- El sondeo de eventos es una aproximación por `hs_lastmodifieddate`, no un webhook de eventos. Para producción con alto volumen se recomienda sustituirlo por webhooks de HubSpot.
- El resumen diario depende de la capacidad de lectura de tareas/actividad y de las propiedades habilitadas en la cuenta.
- El modelo gratuito está sujeto a límites, disponibilidad y cambios del proveedor. Configura el modelo actual habilitado en tu panel de Groq.
- Las operaciones de reunión y nota pueden requerir propiedades/formatos específicos y asociaciones explícitas en tu portal.

## Comandos

- `/start`
- `/ayuda`
- `/cancelar` (la cancelación de una operación se realiza con el botón Cancelar del mensaje pendiente)

## Ejemplos de uso

- `Busca a María García`
- `Crea un contacto con nombre Ana Pérez y email ana@empresa.com`
- `Muéstrame los negocios abiertos`
- `Crea una tarea para llamar a Juan mañana a las 10`
- `Consulta las etapas del pipeline de negocios`
- `¿Qué propiedades personalizadas tiene el objeto contactos?`
