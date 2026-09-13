-- Elimina chat_sessions/chat_messages (creadas en 010_create_chat_sessions.sql).
--
-- Auditado (grep -rn "chat_sessions\|chat_messages" backend/ frontend/): ningún
-- nodo, router ni página del frontend lee o escribe estas tablas. Solo las
-- poblaba data/generate_dataset.py como muestra ilustrativa para el dataset
-- sintético de QA/seed -- nunca el chat en producción. El propósito original
-- ("dar contenido conversacional real con el que probar el futuro Agente de
-- Triaje", ver data/README.md histórico) ya está cubierto, y mejor, por
-- mecanismos que sí están en uso: el historial real de cada conversación vive
-- en el checkpointer de LangGraph (`checkpoints`/`checkpoint_writes`, ver
-- graph.py) y es trazable en Langfuse por `thread_id` = `langfuse_session_id`
-- (con tokens/coste/latencia que chat_messages nunca tuvo). Mantener una tabla
-- sin consumidor real solo añade superficie sin aportar nada -- ver
-- docs/defensaTFM/defenderAgentes.md §15.
--
-- No se elimina/edita 010_create_chat_sessions.sql (migraciones numeradas y
-- secuenciales: no se reescribe el historial, se añade una migración nueva
-- que deshace el efecto de la anterior).
DROP TABLE IF EXISTS chat_messages;
DROP TABLE IF EXISTS chat_sessions;
