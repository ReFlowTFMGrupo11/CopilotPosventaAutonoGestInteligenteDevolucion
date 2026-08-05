
Copiloto de Posventa Autónomo y Gestión Inteligente de Devoluciones (ReFlow)

1. Planteamiento del Problema y Arquitectura Técnica


El problema de negocio
Las devoluciones y consultas de estado de pedido ("¿Dónde está mi paquete?") representan más del 60% del volumen de soporte en e-commerce. Validar si un producto cumple la política de devolución y tramitar la etiqueta de envío consume un tiempo excesivo del equipo humano de atención al cliente.


Arquitectura Técnica del Sistema (Return Workflow)
La arquitectura de la solución se diseña bajo un enfoque modular, separando la persistencia de datos, la orquestación de la inteligencia artificial y la interfaz de usuario. El sistema se compone de los siguientes bloques principales:


1. Servidores MCP (Model Context Protocol)
Actúan como la capa de herramientas e integración externa, permitiendo a los LLMs interactuar con sistemas de forma segura y estandarizada:
MCP Supabase (mcp_supabase.py): Servidor unificado de datos y conocimiento. Gestiona tanto el acceso en tiempo real a la base de datos relacional (historial de pedidos, usuarios, estados en PostgreSQL) como la búsqueda semántica vectorial (RAG sobre políticas de devolución usando pgvector).
MCP Logistics (mcp_logistics.py): Servidor de acciones externas. Actúa como un conector simulado para interactuar con agencias de transporte, emitir etiquetas PDF de devolución y simular el envío de correos electrónicos transaccionales al cliente.

Nota: Para actualizar a la última versión del conector MCP de LangChain, ejecutar:
pip install --upgrade langchain-mcp-adapters


2. Sistema Multi-Agente (LangChain)
El núcleo de razonamiento se implementa como una cadena secuencial de agentes (Chain) dividida en tres agentes especializados para evitar la saturación del contexto del LLM y garantizar la seguridad:
Agente de Triaje y Empatía: Primer punto de contacto. Atiende al usuario, comprende el motivo de su insatisfacción y extrae parámetros clave (como el order_id) de forma conversacional.
Agente Evaluador de Políticas: Actúa como auditor. Consulta el historial del pedido (SQL) y la base vectorial de normas (RAG) para verificar de forma estricta si la devolución es elegible basándose en plazos, categoría del producto y estado.
Agente de Resolución: Si la devolución es elegible, invoca las herramientas logísticas para generar la etiqueta de transporte, registra la devolución en la base de datos y redacta el mensaje final. Incluye una condición de Human-in-the-Loop (HITL) que pausa el estado si el importe a devolver supera los 100€, derivando el caso a un administrador.
3. Backend (FastAPI) y Frontend (Streamlit)
Backend REST y Streaming (FastAPI): Expone los flujos de LangChain como servicios web seguros. Gestiona las sesiones de chat, la persistencia del estado en Supabase y emite las respuestas generadas por los agentes en tiempo real mediante Server-Sent Events (SSE).
Interfaces de Usuario (Streamlit):
Vista Cliente: Chat interactivo donde el usuario final puede tramitar su devolución de forma conversacional y descargar su etiqueta de envío.
Vista Admin: Panel de control (Dashboard) para la supervisión humana. Permite revisar las devoluciones de alto valor pausadas por el sistema y aprobarlas o rechazarlas con un solo clic, reanudando la ejecución del agente.


Tabla de Herramientas (Tools) por Servidor MCP
Servidor MCP
Herramienta (Tool)
Entradas
Descripción y Agente Asignado
mcp_supabase.py

(Datos y Políticas)
get_order_details
order_id
Agentes 1 y 2: Consulta en PostgreSQL los detalles del pedido, fechas y productos comprados.


get_customer_return_history
customer_id
Agente 2: Recupera el historial de devoluciones del cliente para detectar posibles abusos.


search_return_policy
query, category
Agente 2: Realiza una búsqueda semántica RAG usando pgvector sobre la normativa de la tienda.


create_return_record
order_id, monto...
Agente 3: Inserta una solicitud de devolución en la tabla devoluciones de Supabase.


update_return_status
return_id, status
Admin / HITL: Actualiza el estado de la devolución desde el panel de control manual.
mcp_logistics.py

(Logística)
generate_shipping_label
order_id, items
Agente 3: Maqueta un archivo PDF simulado de la etiqueta de transporte utilizando reportlab.


send_customer_notification
email, message...
Agente 3: Simula el envío de un correo electrónico transaccional con el enlace al PDF generado.


2. El Flujo Completo Paso a Paso
El usuario entra en Streamlit: Escribe "Hola, quiero devolver el pedido #12345".
Streamlit hace una llamada HTTP POST: Envía ese texto a http://localhost:8000/api/chat en formato JSON.
FastAPI recibe el JSON: Valida que el texto y el order_id tengan el formato correcto mediante esquemas de Pydantic.
FastAPI despierta a LangChain: Transfiere los datos a la cadena de agentes en ejecución.
Los Agentes trabajan en secuencia:
El Agente de Triaje extrae el identificador #12345.
El Agente Evaluador llama al MCP Supabase (SQL) para comprobar la fecha de compra y al MCP Supabase (RAG/pgvector) para comprobar si el producto admite devolución.
El Agente de Resolución llama al MCP Logistics para crear la etiqueta de envío.
LangChain devuelve el resultado: Notifica la salida final a FastAPI.
FastAPI responde a Streamlit: Envía la estructura JSON final: {"status": "approved", "response": "Tu devolución ha sido aprobada...", "label_url": "http://.../etiqueta.pdf"}.
Streamlit renderiza el resultado: Muestra el mensaje en la pantalla del usuario e incrusta el botón de descarga del PDF.
Resumen del rol de FastAPI: Funciona como la capa de integración limpia, asíncrona y segura entre la interfaz de usuario y el motor multi-agente subyacente.

3. Estimación Global de Tiempos
Épica / Bloque de Trabajo
Horas Estimadas
Porcentaje
Épica 1: Datos y Servidores MCP
20 h
15%
Épica 2: Motor Multi-Agente (LangChain)
35 h
25%
Épica 3: Backend REST y Streaming (FastAPI)
20 h
15%
Épica 4: Frontend e Interfaz Admin (Streamlit)
20 h
15%
Épica 5: Observabilidad, Testing y QA
15 h
10%
Épica 6: Memoria Escrita y Defensa del TFM
30 h
20%
TOTAL
140 h
100%







4. Organización del Backlog (Épicas e Historias de Usuario)
🟢 Épica 1: Capa de Datos en Supabase y Servidores MCP (Semana 1) — 20 horas
Objetivo: Configurar el proyecto en Supabase (PostgreSQL + pgvector) y exponer las herramientas a través del estándar MCP.
US 1.1: Esquema Relacional en Supabase (SQL):
Tarea: Crear script de migración TFM/supabase/migrations/20260101_init_schema.sql con las tablas: users, orders, order_items y returns.
Tarea: Crear script TFM/supabase/seed.sql con 10 pedidos de prueba y casos límite (ej. entregado hace 5 días, entregado hace 40 días, producto no devolvible).
US 1.2: Base Vectorial de Políticas en Supabase (pgvector):
Tarea: Activar la extensión pgvector en Supabase (CREATE EXTENSION IF NOT EXISTS vector;).
Tarea: Crear la tabla policy_chunks con columna de tipo vector(1536) y crear una función RPC en PostgreSQL (match_policies) para búsqueda por similitud de coseno.
Tarea: Redactar politica_devoluciones.md, generar embeddings y cargarlos en la tabla policy_chunks mediante script de ingesta.
US 1.3: Desarrollo de Servidores MCP con SDK de Supabase:
Tarea: Crear TFM/mcp_servers/mcp_supabase.py exponiendo get_order_details, get_customer_history y search_return_policy.
Tarea: Crear TFM/mcp_servers/mcp_logistics.py con la herramienta create_return_label (generador de etiquetas PDF simuladas con reportlab).
🟢 Épica 2: Sistema Multi-Agente en LangChain (Semanas 2 y 3) — 35 horas
Objetivo: Construir el motor de razonamiento multi-agente, la gestión de estado y las reglas de negocio.
US 2.1: Diseño del Estado del Grafo:
Tarea: Definir la estructura ReturnProcessState (TypedDict en TFM/backend/agents/state.py).
US 2.2: Agente 1 (Triaje y Empatía):
Tarea: Diseñar prompt para saludar, entender el problema y extraer order_id e intenciones del usuario.
US 2.3: Agente 2 (Evaluador de Elegibilidad):
Tarea: Diseñar prompt para invocar las herramientas de mcp_supabase.py (datos del pedido + políticas en pgvector).
Tarea: Programar la lógica determinista de validación (Ej. dias <= 30 Y policy_ok == True).
US 2.4: Agente 3 (Resolución y Logística):
Tarea: Diseñar prompt para invocar mcp_logistics.py y redactar el mensaje final de respuesta al cliente.
US 2.5: Lógica Human-in-the-Loop (HITL):
Tarea: Añadir lógica condicional en la cadena de LangChain: si refund_amount > 100€, marcar la devolución como "pendiente_aprobacion" y detener la respuesta automática hasta requerir aprobación manual.
🟢 Épica 3: Backend REST y Streaming en FastAPI (Semana 4) — 20 horas
Objetivo: Exponer los flujos de agentes como servicios web asíncronos y seguros.
US 3.1: Configuración de Endpoints de Chat:
Tarea: Definir esquemas Pydantic v2 de entrada y salida (ChatRequest, ChatResponse).
Tarea: Crear endpoint POST /api/chat/stream con StreamingResponse (SSE) para emitir en tiempo real el razonamiento de los agentes hacia la interfaz.
US 3.2: Endpoints para el Panel de Administración (HITL):
Tarea: Crear endpoint GET /api/admin/pending-returns (listar devoluciones pausadas >100€).
Tarea: Crear endpoint POST /api/admin/approve-return para marcar la devolución como aprobada y disparar la ejecución del Agente de Resolución en LangChain.
US 3.3: Gestión de Persistencia de Sesión:
Tarea: Configurar la persistencia del historial de conversación (memoria de LangChain respaldada en la conexión PostgreSQL de Supabase, o en memoria local durante el desarrollo) para mantener el estado del chat mediante session_id.
🟢 Épica 4: Frontend e Interfaz Admin en Streamlit (Semana 5) — 20 horas
Objetivo: Crear la interfaz de usuario para el cliente y el panel de administración para supervisión humana.
US 4.1: Vista del Cliente (Chat):
Tarea: Crear componente de chat interactivo que consuma el SSE de FastAPI (TFM/frontend/pages/1_💬_Customer_Chat.py).
Tarea: Mostrar información del pedido e incrustar el botón de descarga del PDF de la etiqueta cuando la devolución sea aprobada.
US 4.2: Vista de Administración (Dashboard & HITL):
Tarea: Crear panel lateral de métricas (Devoluciones aprobadas vs. rechazadas vs. escaladas).
Tarea: Crear tabla interactiva para revisar devoluciones pendientes de aprobación manual (>100€) con botones de "Aprobar" y "Rechazar" que llamen a la API de FastAPI.
🟢 Épica 5: Observabilidad, Evaluación y QA (Semana 6) — 15 horas
Objetivo: Auditar llamadas a herramientas, evaluar la calidad de las respuestas y medir rendimiento.
US 5.1: Observabilidad:
Tarea: Conectar LangSmith
 u OpenTelemetry para auditar latencias, uso de herramientas MCP y consumo de tokens.
US 5.2: Evaluación de Calidad (AI as Judge / RAGAS):
Tarea: Crear un Golden Dataset con 15 consultas de prueba guardadas en Supabase o un JSON local.
Tarea: Evaluar métricas de Faithfulness (fidelidad del agente evaluador a las políticas de Supabase) y precisión en la recuperación vectorial con pgvector.
🟢 Épica 6: Redacción de la Memoria y Defensa (Semanas 7 y 8) — 30 horas
Objetivo: Documentar el trabajo realizado y preparar la presentación final del TFM.
US 6.1: Redacción de la Memoria:
Sección 1: Introducción, problema de negocio y objetivos.
Sección 2: Estado del arte (MCP, arquitectura unificada con Supabase/pgvector, sistemas multi-agente).
Sección 3: Arquitectura técnica (diagramas de secuencia de FastAPI, LangChain, MCP y Supabase).
Sección 4: Evaluación, resultados de calidad y análisis de costes.
US 6.2: Preparación de la Defensa:
Tarea: Preparar presentación de diapositivas (15-20 min).
Tarea: Grabar un vídeo de respaldo con la demostración práctica del flujo completo.
5. Cronograma Recomendado (Plan de 8 Semanas)
[Semana 1] ───► Épica 1: Supabase (PostgreSQL + pgvector) + MCP Servers (20h)
[Semana 2] ───► Épica 2: LangChain - Agentes Básicos (18h)
[Semana 3] ───► Épica 2: LangChain - Reglas y Human-in-the-Loop (17h)
[Semana 4] ───► Épica 3: Backend FastAPI + SSE + Persistencia en Supabase (20h)
[Semana 5] ───► Épica 4: Frontend Streamlit (Cliente y Admin) (20h)
[Semana 6] ───► Épica 5: Observabilidad + Evaluación (15h)
[Semana 7] ───► Épica 6: Redacción de la Memoria (15h)
[Semana 8] ───► Épica 6: Ajustes de Memoria + Ensayos de Defensa (15h)
💡 Consejos Clave para no sobrepasar los tiempos
Aplica la filosofía "Menos es Más" en la UI: No pierdas horas personalizando CSS en Streamlit. Con los componentes nativos de st.chat_input, st.chat_message y st.dataframe es más que suficiente para un TFM impecable.
Prioriza los Servidores MCP en Local: Ejecuta los servidores MCP dentro del mismo entorno de Python usando transporte STDIO o HTTP local para evitar problemas de red durante la fase inicial de desarrollo.

Comprobar si los servidores MCP están levantados (puertos 8001/8002):
netstat -ano | findstr ":8001 :8002" | findstr LISTENING

Si no aparece nada, ninguno de los dos está en uso. Si aparecen líneas como estas, el último número de cada fila es el PID del proceso:
  TCP    0.0.0.0:8001           0.0.0.0:0              LISTENING       22476
  TCP    0.0.0.0:8002           0.0.0.0:0              LISTENING       22488

Para apagarlos, matar el proceso por su PID:
taskkill //PID 22476 //F; taskkill //PID 43648 //F

(En Git Bash hay que usar // en lugar de / para que no interprete /PID y /F como una ruta.)

Escribe la Memoria en paralelo: No esperes a la Semana 7 para empezar a escribir. A medida que diseñes la arquitectura en la Semana 3 o los endpoints en la Semana 4, ve guardando los diagramas de arquitectura y explicando las decisiones técnicas en tu documento borrador.

