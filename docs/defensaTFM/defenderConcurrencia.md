# Concurrencia, locks y escalabilidad — Preguntas frecuentes para la defensa

## ¿Por qué hay un lock en el endpoint de chat?

FastAPI procesa peticiones de forma asíncrona y puede atender múltiples
solicitudes en paralelo. Si el usuario hace doble clic en "enviar", o Streamlit
lanza un `st.rerun()` mientras el grafo sigue procesando, llegan **dos peticiones
simultáneas para el mismo `thread_id`**. Sin protección, ambas invocarían
`graph.astream()` sobre el mismo checkpoint de LangGraph, pudiendo corromper el
estado conversacional o generar respuestas duplicadas.

El lock resuelve este caso:

```python
_thread_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

lock = _thread_locks[thread_id]
if lock.locked():
    # Rechaza la segunda petición educadamente
    yield ChatStreamEvent(type="awaiting_admin", content="Ya procesando...")
    return

async with lock:
    # Solo una petición a la vez por thread_id
    await graph.astream(...)
```

---

## ¿Es suficiente el lock en memoria para producción escalada?

**Sí**, para este sistema. El razonamiento es:

### Cómo Streamlit gestiona las sesiones

Cada vez que un usuario abre el navegador, Streamlit crea una sesión nueva con
su propio `st.session_state`. Dentro de ese estado se genera un `thread_id`
único (UUID v4). Por tanto:

$$\text{1 pestaña del navegador} = \text{1 sesión Streamlit} = \text{1 thread\_id único}$$

### Escenario con múltiples contenedores

Con 100 usuarios simultáneos distribuidos en 3 contenedores:

```
Usuario 1 → thread_id="aaa-..." → Contenedor 1
Usuario 2 → thread_id="bbb-..." → Contenedor 2
Usuario 3 → thread_id="ccc-..." → Contenedor 3
```

Los `thread_id` son distintos → nunca colisionan entre contenedores.

### ¿Cuándo sí podría ser un problema?

Solo si el **mismo** `thread_id` llegara a dos contenedores distintos al mismo
tiempo. Para que ocurra necesitaría:

1. El usuario enviando dos mensajes simultáneos desde la misma pestaña, **Y**
2. El balanceador de carga distribuyendo ambas peticiones a contenedores distintos.

En la práctica esto no ocurre porque:
- Streamlit envía peticiones secuencialmente (espera la respuesta antes de
  permitir el siguiente envío).
- Los balanceadores modernos usan **sticky sessions** — el mismo usuario siempre
  va al mismo contenedor.

---

## ¿Qué garantiza la consistencia del estado en múltiples instancias?

El checkpointer de **PostgreSQL** (`AsyncPostgresSaver`). LangGraph persiste el
estado conversacional en la base de datos con transacciones ACID. Dos
contenedores pueden leer y escribir el mismo `thread_id` en la BD sin
corrupción porque PostgreSQL garantiza la consistencia mediante bloqueos a nivel
de fila.

```
Contenedor 1: graph.ainvoke(thread_id="abc") → lee checkpoint → ejecuta → escribe checkpoint
Contenedor 2: graph.ainvoke(thread_id="abc") → espera transacción → lee estado actualizado
```

Esto es exactamente por qué se eligió `AsyncPostgresSaver` sobre `InMemorySaver`
para producción — el estado sobrevive reinicios de servidor y es compartido entre
instancias.

---

## ¿Qué pasaría si se usara solo InMemorySaver en producción?

- El estado conversacional solo existiría en RAM del proceso.
- Si el servidor se reinicia → todas las conversaciones en curso se pierden.
- Si hay varios contenedores → cada uno tiene su propio estado → inconsistencia.
- Los casos HITL pendientes de aprobación admin no sobrevivirían a un reinicio.

Por eso `InMemorySaver` solo se usa en desarrollo local (cuando no hay
`SUPABASE_DB_URL` configurada).

---

## Resumen para la defensa

| Componente | Propósito | Alcance |
|---|---|---|
| `asyncio.Lock` por `thread_id` | Evitar doble invocación del grafo desde la misma sesión | Dentro de 1 proceso |
| `AsyncPostgresSaver` | Persistir estado conversacional entre turnos y reinicios | Distribuido, ACID |
| UUID v4 como `thread_id` | Garantizar unicidad de sesiones | Global |
| Sticky sessions (balanceador) | Evitar que peticiones del mismo usuario lleguen a instancias distintas | Infraestructura |
