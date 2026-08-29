---
name: arquitectura-backend
description: Documents this project's backend architecture decisions and layering rules -- database access must flow through the services layer, the responsibilities of db/ vs services/ vs agents/infra/, why supabase/ and langfuse_infra/ live at the repo root instead of under a shared infra/ folder, and how environment variables must be centralized via pydantic-settings. Use when writing or reviewing backend code, adding a new router/service/agent node, deciding where a new file belongs, touching env vars, or considering folder-structure changes.
---

# Arquitectura del backend

Estas son las decisiones de arquitectura que se deben respetar siempre en
este proyecto. No son sugerencias puntuales: cualquier código nuevo o
refactor debe seguirlas, y cualquier código existente que las incumpla se
considera deuda técnica a corregir, no un patrón alternativo válido.

## 1. Flujo de dependencias: todo pasa por `services/`

```
backend/api/routers/*.py   ┐
backend/mcp/mcp_*.py       ├──►  backend/services/*.py  ──►  backend/db/*.py  ──►  Supabase / Postgres
backend/agents/nodes/*.py  ┘            (lógica de negocio)      (conexión/cliente)
```

**Regla:** ninguna capa de entrada (`api/`, `mcp/`, `agents/nodes/`) importa
`backend/db/` directamente. Todas pasan por `backend/services/`. Solo
`services/` puede importar `db/`.

**Por qué:** `services/` existe precisamente para que la lógica de negocio
(cálculo de días desde entrega, detección de devoluciones duplicadas,
mutaciones sobre pedidos) sea reutilizable desde cualquier consumidor —
FastAPI, MCP, un nodo de LangGraph, un script — sin arrastrar detalles de
conexión ni de protocolo de transporte.

**Deuda conocida (pendiente, fuera de `backend/`):**
- `data/rag/ingest_policy_embeddings.py` importa `get_supabase_client`
  directo, saltándose `supabase_service.py`. Menor prioridad: es un script
  standalone fuera de `backend/`, no parte del grafo de servicio.

## 2. `db/` vs `services/`: no fusionar

- `backend/db/` = *conexión y autenticación* (bootstrapping de clientes,
  singleton cacheado). Sin lógica de negocio.
- `backend/services/` = *lógica de negocio*. Es la única capa que importa
  `db/`.

No mover el cliente de `db/` dentro de `services/` aunque hoy `db/` tenga un
solo archivo (`supabase_client.py`). Si aparece una segunda vía de conexión
(p. ej. el pool `psycopg` crudo que `backend/agents/graph.py` crea inline
para el checkpointer de LangGraph vía `SUPABASE_DB_URL`), esa conexión
también debería vivir en `db/`, no inline en `agents/`. `db/` está
infrautilizada, no sobre-diseñada.

## 3. `backend/agents/infra/`: adaptadores técnicos, no lógica de negocio ni SQL

`backend/agents/infra/` sigue un sentido de arquitectura hexagonal/clean:
adaptadores que hablan con sistemas externos (p. ej. `mcp_client.py`, un
cliente HTTP hacia los MCP servers). No debe contener:
- Lógica de negocio (motivo por el que existió la rama
  `refactor/mover-llm-factory-fuera-de-infra`: `llm_factory.py` no es un
  adaptador, es una decisión de negocio sobre qué modelo/parámetros usar).
- Esquema o migraciones de base de datos (eso vive en `supabase/`, ver punto 4).

## 4. `supabase/` y `langfuse_infra/` en la raíz, no bajo un `infra/` compartido

- `supabase/` (migraciones SQL, seed) debe quedarse en la raíz del repo, sin
  anidar bajo `infra/`. Es una convención de la CLI de Supabase: busca
  `supabase/config.toml` subiendo desde el cwd, y anidarlo obligaría a pasar
  `--workdir` en cada comando si el proyecto adopta la CLI.
- El repo ya sigue el patrón "una carpeta top-level por cada infraestructura
  externa" (`langfuse_infra/` es su propio hermano de `backend/`,
  `frontend/`, etc.), no "una carpeta `infra/` compartida con subcarpetas".
  Mantener esa consistencia; no introducir un `infra/` nuevo.

## 5. Variables de entorno: centralizadas, tipadas, una sola fuente de verdad

- Todas las env vars del backend viven en `backend/config.py`
  (`Settings` + `get_settings()`, cacheado vía `@lru_cache`). Nunca
  `os.getenv()` suelto por el código ni objetos de settings nuevos —
  extender `Settings`, no crear uno paralelo.
- Una sola lectura por variable: no duplicar el mismo valor en varios
  archivos (ej. `GRAPH_RECURSION_LIMIT` estaba duplicado de forma
  independiente en `chat.py` y `admin.py` antes de centralizarlo).
- Los campos son opcionales con default seguro en `Settings` (nada
  obligatorio ahí), para que importar `Settings` desde un módulo no
  relacionado con Supabase (p. ej. `llm_factory.py`) nunca falle por
  falta de credenciales de BD. La validación de "falla rápido si falta
  algo" vive en el único sitio que de verdad lo necesita: p. ej.
  `get_supabase_client()` lanza un `RuntimeError` explícito si faltan
  `SUPABASE_URL`/`SUPABASE_SERVICE_KEY`, en vez de ser un campo
  obligatorio de `Settings` que acoplaría todo lo demás a Supabase.
- El nombre del campo debe coincidir exactamente (en mayúsculas) con lo
  documentado en `.env.example` y `README.md`.
- Los secretos (`supabase_service_key`, `openai_api_key`,
  `langfuse_secret_key`) tipados como `pydantic.SecretStr`, para que no
  se filtren accidentalmente en logs o tracebacks.
- El `.env` se carga una sola vez, vía `env_file` de `pydantic-settings`
  dentro de `Settings` — no con `load_dotenv()` repetido en módulos
  sueltos.

## 6. Comentarios: concisos y al grano

Ni `black` ni `flake8` (ver `README.md` → "Linting y formato") juzgan la
verbosidad de un comentario: `black` no reescribe texto, y `flake8` solo
limita la longitud de línea (`E501`), lo que fuerza a envolver una frase
larga en más líneas, no a acortarla. Es una convención a aplicar en
código nuevo y en review, no algo que una herramienta detecte:

- Explica el **porqué** (una decisión no obvia, un bug que se evitó, una
  limitación conocida), no el **qué** — el código ya dice qué hace.
- Si necesitas más de 3-4 líneas para justificar algo, es señal de que
  el código en sí debería ser más claro, o el detalle pertenece a un doc
  separado (`docs/`), no a un comentario inline.
- No repitas en prosa lo que ya está en el nombre de la función/variable.

## Al revisar o escribir código nuevo

Antes de añadir un archivo nuevo o una llamada a base de datos, comprobar:
1. ¿Esta lógica de negocio va en `services/`, no directamente en el router,
   la tool MCP o el nodo del agente?
2. ¿El acceso a la BD pasa por `services/`, no importa `db/` directamente?
3. ¿La variable de entorno nueva se lee desde `backend/config.py`
   (`get_settings()`), no con un `os.getenv()` nuevo?
4. ¿El nombre de la variable coincide exactamente entre código, `.env.example`
   y `README.md`?
5. ¿Los comentarios explican el porqué, no el qué, y son concisos (ver
   punto 6)?
