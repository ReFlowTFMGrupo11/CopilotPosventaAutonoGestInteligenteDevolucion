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

**Deuda conocida a corregir cuando se toque ese código:**
- `backend/agents/nodes/resolution.py` importa `get_supabase_client` directo
  desde `backend.db.supabase_client`, saltándose `supabase_service.py`.
- `data/rag/ingest_policy_embeddings.py` hace lo mismo (menor prioridad: es
  un script standalone fuera de `backend/`, no parte del grafo de servicio).

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

- Centralizar en un objeto de configuración tipado con `pydantic-settings`
  (`BaseSettings`), ya es una dependencia declarada en `requirements.txt` y
  ya hay un ejemplo correcto en `backend/db/supabase_client.py`
  (`SupabaseSettings` + `@lru_cache`). Extender ese patrón, no inventar uno
  nuevo ni usar `os.getenv()` suelto por el código.
- Una sola lectura por variable. No duplicar el mismo `os.getenv(...)` con el
  mismo default en varios archivos.
  **Deuda conocida:** `GRAPH_RECURSION_LIMIT` y `GRAPH_TURN_TIMEOUT_SECONDS`
  están definidos de forma independiente con el mismo default en
  `backend/api/routers/chat.py` y `backend/api/routers/admin.py`.
- Fallar rápido: las variables requeridas sin default deben lanzar un error
  claro al arrancar (vía `BaseSettings` sin default), no propagar `None` en
  silencio hasta fallar más adelante con un error críptico.
- El nombre real de la variable en el código debe coincidir exactamente con
  lo documentado en `.env.example` y `README.md`.
  **Deuda conocida:** `.env.example`/`README.md` documentan `SUPABASE_URL`,
  pero `SupabaseSettings.supabase_api_url` en realidad requiere
  `SUPABASE_API_URL` — mismatch pendiente de corregir.
- Los secretos (API keys, service keys) deben tipar como `pydantic.SecretStr`
  para que no se filtren accidentalmente en logs o tracebacks.
- El `.env` se carga una sola vez (vía `env_file` de `pydantic-settings`), no
  con `load_dotenv()` repetido en varios módulos.

## Al revisar o escribir código nuevo

Antes de añadir un archivo nuevo o una llamada a base de datos, comprobar:
1. ¿Esta lógica de negocio va en `services/`, no directamente en el router,
   la tool MCP o el nodo del agente?
2. ¿El acceso a la BD pasa por `services/`, no importa `db/` directamente?
3. ¿La variable de entorno nueva se lee desde el objeto de settings
   centralizado, no con un `os.getenv()` nuevo?
4. ¿El nombre de la variable coincide exactamente entre código, `.env.example`
   y `README.md`?
