# Defender el pipeline de CI de ReFlow

Este documento recoge los argumentos para defender, en la memoria/presentación del
TFM, las decisiones tomadas en `.github/workflows/ci.yml`: qué se comprueba en cada
PR, qué bloquea el merge y qué no, y por qué se dejó fuera deliberadamente todo lo
que necesitaría infraestructura real o gastar dinero en cada ejecución.

Es CI, no CI/CD: el pipeline no despliega nada. Solo valida un PR antes de mergear.

## 1. Nueve jobs en paralelo, no encadenados

### El planteamiento
`ci.yml` define 9 jobs (`lint`, `test`, `secrets-scan`, `validate-drawio`,
`rag-ingest-dry-run`, `qa-golden-dataset-dry-run`, `smoke-boot`, `typecheck`,
`dependency-audit`) que corren **todos a la vez**, no uno detrás de otro con
`needs:`.

### Argumentos para defenderlo
- **Feedback más rápido:** si `flake8` falla, quien abrió el PR lo sabe en el mismo
  tiempo que si hubiera fallado `pytest`, no después de esperar a que `lint`
  termine primero. Encadenarlos solo tendría sentido si un job dependiera del
  resultado de otro (no es el caso: ninguno necesita el artefacto de otro).
- **Coste real de CI en GitHub Actions:** minutos de runner en paralelo cuestan
  exactamente lo mismo en tiempo-de-reloj que en serie (se pagan por minuto de
  runner, no por minuto de pared); lo único que cambia es cuánto tarda el
  desarrollador en enterarse de que algo falló.
- **Aislamiento de fallos:** un job que se cuelga o tarda mucho (ver el bug de
  `curl` sin `--max-time` en `smoke-boot`, sección 4) no bloquea a los demás.

## 2. Qué bloquea el merge y qué no — y por qué esa línea concreta

### El planteamiento
7 de los 9 jobs son bloqueantes. `typecheck` (mypy) y `dependency-audit`
(pip-audit) llevan `continue-on-error: true`: el job se ejecuta y reporta, pero un
fallo suyo no impide mergear.

### Argumentos para defenderlo
- **mypy no bloquea porque nunca se había corrido antes.** Al introducirlo por
  primera vez sobre un código ya escrito, encontró **107 errores de tipos reales**
  en 9 archivos (principalmente `str | None` pasado donde se esperaba `str`).
  Bloquear el merge de inmediato con eso habría parado todo el repo el día que se
  añadió la herramienta, sin haber limpiado nada previamente. La secuencia
  correcta es: introducir en modo informativo → limpiar el volumen inicial →
  hacerlo bloqueante una vez el ruido de fondo sea cero.
- **pip-audit tampoco bloquea, por la misma razón de "primera introducción",**
  aunque en este caso no encontró ninguna vulnerabilidad conocida al añadirlo — se
  deja informativo de todas formas por consistencia con el criterio anterior, no
  porque haya encontrado un problema real que justifique retrasar el bloqueo.
- **Los otros 7 sí bloquean desde el primer commit** porque no tienen ese problema
  de "volumen heredado": `black`/`flake8` se comprobaron contra el repo antes de
  activarlos (37 de 63 archivos habrían cambiado con `black`, pero **no se
  aplicó** — se dejó para un commit de formato aparte, revisable por sí solo,
  precisamente para no mezclar un diff de reformateo masivo con la introducción de
  la herramienta), y el resto (tests, secrets, drawio, RAG dry-run, smoke-boot) ya
  pasaban en verde al añadirlos.

## 3. Los checks del pipeline RAG/LLM no llaman a ningún LLM

### El planteamiento
`rag-ingest-dry-run` y `qa-golden-dataset-dry-run` validan, respectivamente, el
chunking de las 17 políticas Markdown y la consistencia de los 480 casos del
golden dataset (`evaluation/golden/eval_cases.csv`) contra las reglas deterministas de
`policy_rules.py` — sin ninguna llamada real a OpenAI ni a Supabase.

### Argumentos para defenderlo
- **No se construyó nada nuevo para esto:** ambos scripts (`ingest_policy_
  embeddings.py`, `evaluate_evaluator_agent.py`) ya tenían su propio flag `--dry-run` pensado
  para exactamente este uso — uno de los dos dice literalmente *"Ideal para CI"*
  en su propio docstring. Simplemente no había ningún workflow que los invocara
  todavía; conectarlos a CI fue coste casi cero.
- **`evaluate_evaluator_agent.py --dry-run` valida los 480 casos en menos de 1 segundo** y ya
  trae su propio gate de pass/fail (`sys.exit(0 if accuracy >= 0.70 else 1)`),
  reutilizado tal cual — no se inventó un umbral nuevo.
- **Lo que deliberadamente NO se hizo:** correr `evaluate_evaluator_agent.py` sin `--dry-run`
  (el eval real contra `gpt-5-mini`, 480 llamadas de verdad a OpenAI) en cada PR.
  Eso sí sería la prueba de regresión de prompts genuina — pero cuesta dinero por
  ejecución, necesita `OPENAI_API_KEY` como secret del repo, y el resultado varía
  entre ejecuciones (el LLM no es determinista). Es el mismo argumento que en la
  sección 5: coste + no-determinismo son mal combo para un gate que se ejecuta en
  cada PR. Queda propuesto como workflow aparte, manual o programado.

## 4. `smoke-boot`: arrancar los 3 servicios de verdad

### El planteamiento
`smoke-boot` levanta `mcp_supabase.py`, `mcp_logistics.py` y la API FastAPI como
procesos reales en background (sin ningún `.env` — todo cae a los defaults de
`Settings`, ver `backend/config.py`), y comprueba con `curl` que los 3 responden.

### Argumentos para defenderlo
- **Cubre una clase de bug que ningún otro job ve.** `pytest` importa los módulos
  directamente y todo está mockeado — nunca ejecuta el bloque `if __name__ ==
  "__main__":` real. `flake8`/`mypy` son análisis estático, no ejecutan nada. Si
  alguien rompe el entrypoint (`backend/api/run.py`), cambia un puerto sin
  querer, o se olvida una dependencia de arranque en `requirements.txt`, ninguno
  de los otros 8 jobs lo detectaría — `smoke-boot` sí.
- **No necesita ni Postgres real ni `OPENAI_API_KEY`,** porque no hace ninguna
  petición de negocio (no llama a `/api/chat`) — solo confirma que cada proceso
  arranca y su servidor HTTP acepta conexiones. Verificado en local: `/health`
  responde `200`, y los dos MCP servers responden `406` a un `GET` simple (código
  esperado: streamable-HTTP exige cabeceras específicas que un `curl` normal no
  manda, pero el `406` en sí ya prueba que el servidor está arriba).
- **Un bug real, encontrado y corregido en el propio desarrollo de este job:**
  los servidores MCP no cierran la conexión ante un `GET` sin las cabeceras
  correctas (se quedan esperando una negociación SSE que nunca llega). El primer
  intento de este check, sin `curl --max-time`, se quedó colgado indefinidamente
  en local — reproducible, no una casualidad del entorno. El fix (`--max-time 5`
  en cada `curl`) se verificó antes de subir el commit, no se dedujo solo de la
  documentación de `curl`.

## 5. Por qué no hay un test end-to-end con LLM y base de datos reales

### El planteamiento
Ni `smoke-boot` ni ningún otro job hacen una petición real de negocio (`POST
/api/chat`) que dispare al LLM de verdad contra una base de datos real.

### Argumentos para defenderlo
- **Determinismo:** un LLM no da la misma respuesta dos veces con el mismo
  prompt. Un test que compara "¿la respuesta contiene X?" contra un LLM real es
  intrínsecamente inestable como *gate* de merge — fallaría unas veces sí, otras
  no, sin que el código haya cambiado. Un CI que falla por azar entrena al equipo
  a ignorar sus fallos ("total, es que el LLM..."), que es peor que no tenerlo.
- **Coste:** cada ejecución llamaría a la API de OpenAI de verdad. En 20 PRs al
  día, son 20 ejecuciones pagadas de algo que no aporta una señal fiable (por el
  punto anterior).
- **Infraestructura:** necesitaría Postgres con la extensión `pgvector` (vía
  `services:` de GitHub Actions), correr las migraciones de `supabase/`, y
  gestionar `OPENAI_API_KEY`/`SUPABASE_SERVICE_KEY` como secrets del repo — mucha
  superficie nueva para un beneficio marginal, dado que la lógica de negocio
  (routing del grafo, reglas deterministas, capas de servicios) ya está cubierta
  por `test` con mocks, que sí es determinista y gratis.
- **Lo que sí se propuso** (y queda documentado, no implementado): un workflow
  separado, manual o programado (no en cada PR), para el eval real de
  `evaluate_evaluator_agent.py` contra el golden dataset — ahí el no-determinismo se mitiga
  promediando sobre 480 casos en vez de comparar una sola respuesta.

## 6. Secret scanning con `trufflehog`, pineado a una versión concreta

### El planteamiento
`secrets-scan` corre `trufflesecurity/trufflehog@v3.97.1` con `--only-verified`
sobre el diff del PR.

### Argumentos para defenderlo
- **Por qué importa en este proyecto en concreto:** el backend maneja
  `SUPABASE_SERVICE_KEY` y `OPENAI_API_KEY` reales (ver `backend/config.py`,
  `SecretStr`). Un `.env` commiteado por error sigue siendo, en la práctica, el
  incidente de seguridad más común y más barato de prevenir con una sola acción
  de CI.
- **`--only-verified`:** reduce falsos positivos comprobando contra la API del
  proveedor si la credencial detectada está realmente activa, en vez de marcar
  cualquier string con pinta de API key.
- **Versión pineada a un tag concreto, no `@main`:** usar una rama en vez de un
  tag/SHA es un riesgo de cadena de suministro (supply chain) — el contenido de
  `@main` puede cambiar sin aviso entre una ejecución y la siguiente. Se fijó a
  la última release estable en el momento de escribir el workflow.

## 7. Preguntas típicas de la defensa

**¿Este pipeline garantiza que el código en producción funciona?**
No, y hay que ser honesto con esta pregunta. Garantiza que el código pasa
`black`/`flake8`, que la suite de tests mockeada sigue en verde, que no hay
secretos filtrados, que los diagramas no están corruptos, que el pipeline
RAG/dataset es internamente consistente, y que los 3 servicios arrancan sin
crashear. No garantiza que una conversación real con un cliente real, contra un
LLM real y una base de datos real, se comporte como se espera — eso es
precisamente lo que la sección 5 explica que se dejó fuera a propósito, por
coste y no-determinismo.

**Si `mypy` encuentra 107 errores y nunca se arreglan, ¿de qué sirve tenerlo en
CI?**
Hoy, de poco más que visibilidad: cualquiera puede ver en el resumen del PR
cuántos hay y si suben o bajan, sin que eso bloquee a nadie. El valor real
llega el día que se decida limpiar ese volumen inicial (probablemente por
módulos, no de golpe) y activar `continue-on-error: false` — a partir de ahí sí
bloquea. Tenerlo informativo desde ya evita que el volumen crezca sin que nadie
se dé cuenta mientras se decide cuándo hacer esa limpieza.

**¿Por qué tres PRs en cascada (#35 → #36 → #37) en vez de una sola PR grande
con todo?**
Cada rama depende técnicamente de la anterior (el CI necesita `flake8`/`black`
ya declarados en `requirements.txt`, que a su vez se añadieron sobre la rama que
ya tenía corregidos los tests preexistentes), pero son conceptualmente
independientes: arquitectura de capas y env vars (#35), herramientas de lint
(#36), pipeline de CI (#37). Revisar y aprobar cada uno por separado es más
manejable que un diff único que mezcle refactors de `backend/config.py` con la
sintaxis de un workflow YAML.

**¿Por qué no simplemente correr todo en un job único con `needs:` en cadena?**
Se consideró, pero no hay ninguna dependencia real de datos entre los jobs
(ninguno consume un artefacto que otro produzca) — solo dependencia de
*prioridad* percibida ("si el lint falla, para qué seguir"). Encadenarlos solo
haría más lenta la retroalimentación sin ahorrar coste real de CI (ver sección
1).
