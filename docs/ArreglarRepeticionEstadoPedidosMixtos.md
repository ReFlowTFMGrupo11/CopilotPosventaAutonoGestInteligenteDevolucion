# Arreglar repetición de pregunta de estado en pedidos mixtos

## Síntoma observado en QA

En pedidos con **más de un artículo** (p. ej. `ORD-QAM-0002`: Microondas +
Champú), el flujo era:

1. Agente: "¿Cuál quieres devolver y por qué motivo?"
2. Usuario: "Quiero devolver: Microondas Digital 20L, Champu Anticaspa 400ml"
3. Agente: pide el motivo.
4. Usuario: "MICROHONDAS ESTROPEADO, CHAMPU NO ME GUSTA EL COLOR"
5. Agente: **vuelve a preguntar** "¿en qué estado está exactamente?" para el
   Microondas, aunque el usuario ya dijo "estropeado" en el paso 4.

## Causa raíz

Código: `backend/agents/nodes/triage.py`.

El flujo NO es una máquina de estados con slots explícitos: en cada turno se
manda todo el historial de mensajes a un único LLM (`triage_agent`,
`triage.py:100-148`) con salida estructurada (`TriageOutput`). El propio LLM
decide, sin ayuda, qué va en `reason` y qué va en `condition` de cada item.
`backend/agents/graph.py:69-79` (`_has_valid_items_to_return`) corta el turno
en cuanto **cualquier** item tiene `condition` vacío o `"unknown"`, y
`route_after_fetch` (`graph.py:107-120`) hace que el turno termine ahí, a la
espera de que el agente vuelva a preguntar en el siguiente mensaje.

Se identificaron dos causas concretas, ambas en `triage.py`:

1. **`_build_items_prompt` (líneas ~237-260):** la rama de 1 solo artículo
   pedía motivo *y* estado en el mismo mensaje ("¿...y en qué estado se
   encuentra el artículo...?"), pero la rama de **varios artículos** solo
   pedía el motivo ("¿Cuál quieres devolver y por qué motivo?"), sin mencionar
   el estado en ningún momento. Por eso el usuario respondía solo con el
   motivo, sin saber que el estado también hacía falta, y el agente tenía que
   pedirlo después, en otro turno, artículo por artículo.

2. **`TRIAGE_SYSTEM_PROMPT` (líneas ~51-83):** el prompt solo enumeraba los 5
   valores del enum (`unopened, defective, damaged, used, wrong_item`), sin
   ningún mapeo de vocabulario coloquial. No había ninguna instrucción que le
   dijera al LLM "si el motivo ya implica el estado (p. ej. 'estropeado'),
   rellena `condition` con ese valor y no lo vuelvas a preguntar". Al no tener
   esa guía, el modelo dejaba `condition` en `"unknown"` para el Microondas
   pese a que el usuario ya había dicho "estropeado", lo que disparaba de
   nuevo la ruta de "faltan datos" en `graph.py`.

No existe (ni existía) un mapeo determinista de palabras libres → `condition`
para pedidos con varios artículos. El único mapeo determinista del código,
`_CONDITION_MAP` (`triage.py:273-279`), solo se usa dentro de
`_auto_select_single_item`, que **solo se activa si el pedido tiene
exactamente 1 artículo** (`triage.py:286-287`). En pedidos mixtos, todo
dependía de que el LLM adivinara bien sin ayuda.

## Cambios implementados

Archivo modificado: `backend/agents/nodes/triage.py`.

### 1. `TRIAGE_SYSTEM_PROMPT` — nueva sección "Vocabulario coloquial → condition"

**Dónde:** justo después de la definición de los campos a extraer
(`items_to_return` / condiciones posibles), antes de la sección "Artículos
del pedido".

**Qué se añadió:** una tabla de equivalencias explícita entre expresiones
coloquiales típicas en español y los 5 valores del enum:

- "estropeado", "roto", "no funciona", "no enciende", "defectuoso" → `defective`
- "dañado", "golpeado", "llegó dañado", "abollado" → `damaged`
- "sin abrir", "precintado", "nuevo", "no me gusta" (intacto) → `unopened`
- "usado", "ya lo he usado", "lo he probado" → `used`
- "no es el que pedí", "artículo equivocado" → `wrong_item`

Junto con una instrucción explícita: si el motivo de un artículo ya deja claro
su estado, rellenar `condition` **en el mismo turno**, y solo volver a
preguntar el estado de los artículos cuya condición siga siendo ambigua
después de leer todo el historial.

**Por qué:** era la causa principal del bug. Sin este mapeo, el LLM no tenía
ninguna guía para traducir "estropeado" a `defective`/`damaged`, así que lo
dejaba en `unknown` y el grafo forzaba una nueva pregunta redundante. Al ser
un prompt de sistema y no un mapeo por código, cubre tanto pedidos de 1
artículo como mixtos, y cualquier expresión que el LLM ya entienda como
sinónimo razonable de las listadas.

### 2. `_build_items_prompt` — la rama multi-artículo ahora también pide el estado

**Dónde:** rama `else` (pedidos con más de 1 artículo), mensaje final de la
función.

**Antes:**
```python
f"{items_text}\n\n¿Cuál quieres devolver y por qué motivo?"
```

**Después:**
```python
f"{items_text}\n\n¿Cuál quieres devolver, por qué motivo y en qué estado "
f"se encuentra cada uno (sin abrir, defectuoso, dañado, usado, artículo "
f"incorrecto)?"
```

**Por qué:** alinea la rama multi-artículo con la rama de 1 artículo, que ya
pedía motivo + estado en el mismo mensaje. Así el usuario tiene la
oportunidad de dar ambos datos a la vez desde el primer mensaje (como de
hecho intentó hacer en el caso de QA con "estropeado"), reduciendo turnos de
conversación innecesarios en vez de depender de una segunda pregunta que el
LLM podía o no encadenar bien.

## Por qué no se tocó `graph.py`

`_has_valid_items_to_return` y `route_after_fetch` (`graph.py:69-120`) actúan
correctamente dado su contrato: cortar el turno si falta el estado de
*algún* artículo. El problema no era esa validación en sí, sino que el
`condition` llegaba mal relleno (o vacío) desde `triage_agent` porque le
faltaba contexto/instrucciones para interpretarlo. Arreglar la extracción en
el origen (prompt) es más robusto que añadir lógica ad-hoc de "no repitas la
pregunta" en el enrutado del grafo.

## Fase 2 — Blindaje semántico + confirmación explícita

La lista de sinónimos de la Fase 1 no escala: es un parche que nunca cubre
todas las formas de lenguaje natural posibles en las 16 categorías del
catálogo (calzado, mascotas, joyería, alimentación...). En vez de seguir
ampliándola, se optó por dejar que el LLM interprete el motivo **por
significado** (ya es una tarea en la que un modelo de lenguaje es fiable) y
añadir una **confirmación explícita determinista** como red de seguridad
antes de que el grafo avance a la evaluación de elegibilidad.

### 3. `TRIAGE_SYSTEM_PROMPT` — de "tabla de sinónimos" a "interpretación semántica + confirmación"

**Dónde:** misma sección que en la Fase 1, `backend/agents/nodes/triage.py`.

**Qué cambió:**
- La tabla de sinónimos pasa de ser una lista cerrada ("si dice exactamente
  esta palabra, mapea a X") a un conjunto de *ejemplos orientativos*, con la
  instrucción explícita de **no buscar coincidencias literales de palabras
  clave** sino interpretar el significado real de la frase, sea cual sea la
  categoría del producto.
- Se añadió una sección nueva, "Confirmación obligatoria": la primera vez que
  el LLM completa la condición de todos los artículos por inferencia
  semántica, **no debe darla por buena todavía**. Tiene que resumírsela al
  cliente artículo a artículo (p. ej. "entiendo que el Microondas está
  estropeado —lo marco como defectuoso—, ¿es correcto?") y solo marcar
  `items_confirmed = true` en el turno en el que el cliente responde
  confirmando explícitamente ("sí", "correcto", "exacto"...).

**Por qué:** la interpretación semántica libre es más potente y escalable que
una tabla de sinónimos, pero también menos determinista/auditable: el LLM
puede malinterpretar una frase ambigua. Pedir confirmación explícita antes de
avanzar convierte cualquier error de interpretación en una pregunta más para
el cliente, en vez de en una devolución mal tramitada.

### 4. `TriageOutput.items_confirmed` — nuevo campo (`backend/models/returns.py`)

Campo `Optional[bool]` que el LLM rellena `true` solo cuando el último mensaje
del cliente confirma explícitamente el resumen ya mostrado. Es la señal que
usa el código para saber si debe fiarse de la condición inferida.

### 5. `ReturnState.items_confirmed` — nuevo campo de estado (`backend/models/state.py`)

Persiste esa confirmación entre turnos, igual que `reason` o
`items_to_return`.

### 6. Red de seguridad determinista en `triage_agent` (`triage.py`)

**Dónde:** dentro de `triage_agent`, antes de llamar a
`_apply_deterministic_selection`.

**Qué se añadió:** un helper `_items_key()` que genera una firma
`(order_item_id, condition)` de la lista de artículos, y la siguiente regla,
en código (no solo en el prompt, para no depender 100% de que el LLM la
respete):

```python
if _items_key(old_items) != _items_key(new_items):
    updates["items_confirmed"] = False   # acaban de cambiar -> no está confirmado
elif result.items_confirmed:
    updates["items_confirmed"] = True    # sin cambios + LLM dice que confirmó -> nos fiamos
```

**Por qué:** no basta con que el prompt le pida al LLM que no confirme en el
mismo turno en que infiere el estado — un LLM puede equivocarse también en
eso. Esta comprobación ignora cualquier `items_confirmed=true` que el LLM
devuelva si el contenido de `items_to_return` (artículo+condición) acaba de
cambiar respecto al turno anterior, así que la confirmación real solo puede
darse en un turno posterior sobre un resumen que el cliente ya vio.

### 7. `_apply_deterministic_selection` — confirmación automática en selección por checkboxes

**Dónde:** `triage.py`, al final de la función.

**Qué cambió:** cuando el cliente selecciona artículos por checkboxes de la
UI (no texto libre) y la condición ya es conocida, se marca
`items_confirmed = True` directamente; si la condición sigue siendo
`"unknown"`, se marca `items_confirmed = False` explícitamente.

**Por qué:** una selección por checkbox de UI ya es una acción determinista y
explícita del usuario (no una inferencia semántica sobre texto libre), así
que no tiene sentido pedirle un "sí" adicional — el blindaje de confirmación
solo es necesario para lo que el LLM infiere de lenguaje natural.

### 8. `route_after_fetch` — nueva puerta de enrutado (`backend/agents/graph.py`)

**Dónde:** después de `_has_valid_items_to_return` y `_has_reason_data`.

**Qué se añadió:**
```python
def _items_confirmed(state: ReturnState) -> bool:
    return bool(state.get("items_confirmed"))
```
y en `route_after_fetch`:
```python
if not _items_confirmed(state):
    return "__end__"
return "evaluator"
```

**Por qué:** es la puerta que hace efectivo el blindaje: aunque
`items_to_return` tenga condiciones válidas y haya motivo, el grafo no pasa al
Evaluador (que ya calcula elegibilidad/reembolso) hasta que
`items_confirmed` sea `True`. Así el turno termina mostrando el resumen y
esperando confirmación, en vez de arriesgarse a tramitar una devolución sobre
una condición mal inferida.

### Por qué no se usó un clasificador semántico por embeddings

Se valoró (y se descartó por ahora) construir un catálogo de frases canónicas
por categoría y comparar por similitud vectorial contra
`dataset/policies/*.md`. Es más determinista/auditable, pero añade
infraestructura (embeddings, almacenamiento vectorial, mantenimiento del
catálogo por categoría) que no aporta tanto una vez que existe la
confirmación explícita: cualquier fallo de interpretación semántica del LLM
queda atrapado por el paso de confirmación antes de tener consecuencias.

## Validación pendiente

Repetir el caso de QA de `ORD-QAM-0002` (Microondas "estropeado" + Champú
"no me gusta el color") y comprobar que:
- En el turno en el que el cliente da los motivos, el agente responde con un
  resumen artículo a artículo (condición inferida) y pide confirmación, sin
  volver a preguntar "¿en qué estado está exactamente?" por separado.
- El grafo NO avanza al Evaluador en ese turno (`items_confirmed` sigue en
  `False`).
- Al responder "sí, correcto", el agente pasa a evaluar la elegibilidad sin
  pedir nada más.
- Si el cliente corrige algo del resumen, el agente actualiza esa condición y
  vuelve a pedir confirmación (no dispara evaluación con datos no
  ratificados).
- Comprobar también el camino de selección por checkboxes de UI (no debería
  pedir confirmación adicional una vez la condición es conocida).
