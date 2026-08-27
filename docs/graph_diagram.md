# Diagrama del Grafo de Devoluciones (LangGraph)

## Flujo general

```mermaid
graph TD
    START([START]) --> TRIAGE[🤖 Triage Agent<br/>Extrae: order_id, reason, items]
    
    TRIAGE --> ROUTE_T{route_after_triage<br/>¿order_id AND items?}
    
    ROUTE_T -->|NO - falta info| END_WAIT([END<br/>Espera siguiente mensaje])
    ROUTE_T -->|SÍ - todo completo| FETCH[📦 Fetch Order Data<br/>MCP → Supabase]
    
    FETCH --> ROUTE_F{route_after_fetch<br/>¿Error?}
    
    ROUTE_F -->|SÍ - error| END_ERR([END<br/>Pide corrección al usuario])
    ROUTE_F -->|NO - datos OK| EVAL[📋 Evaluator Agent<br/>RAG políticas + verificación]
    
    EVAL --> ROUTE_E{route_after_evaluator<br/>¿Elegible?}
    
    ROUTE_E -->|NO| REJECT[❌ Rejection Agent<br/>Mensaje empático de rechazo]
    ROUTE_E -->|SÍ| RESOLVER[✅ Resolution Agent<br/>Crea devolución + etiqueta]
    
    REJECT --> END_R([END])
    
    RESOLVER --> ROUTE_HITL{¿Importe > 100€?}
    ROUTE_HITL -->|NO| END_OK([END<br/>Devolución completada])
    ROUTE_HITL -->|SÍ| HITL[👤 HITL Admin<br/>Aprobación humana]
    
    HITL --> END_HITL([END])
```

## Ejemplo de conversación multi-turno

```mermaid
sequenceDiagram
    participant U as Usuario
    participant D as chat.py (API)
    participant G as LangGraph
    participant T as Triage Agent
    participant CP as Checkpointer
    participant MCP as MCP Server

    Note over U,MCP: Turno 1 - Saludo
    U->>D: "hola quiero devolver"
    D->>G: ainvoke({messages: [Human("hola...")]})
    G->>CP: Restaurar estado (vacío, primer turno)
    G->>T: triage_agent(state)
    T->>T: LLM extrae: order_id=None, items=None
    T-->>G: {messages: [AI("¿order_id?")], order_id: None}
    G->>G: route_after_triage → END (falta info)
    G->>CP: Guardar estado
    G-->>D: result
    D-->>U: "¿Podrías compartirme el order_id?"

    Note over U,MCP: Turno 2 - Order ID
    U->>D: "c9d0e1f2-..."
    D->>G: ainvoke({messages: [Human("c9d0e1f2-...")]})
    G->>CP: Restaurar estado (tiene historial previo)
    G->>T: triage_agent(state) con 3 messages
    T->>T: LLM extrae: order_id=✅, items=None
    T-->>G: {order_id: "c9d0e1f2-...", messages: [AI("¿motivo?")]}
    G->>G: route_after_triage → END (faltan items)
    G->>CP: Guardar estado
    G-->>D: result
    D-->>U: "¿Cuál es el motivo?"

    Note over U,MCP: Turno 3 - Motivo + item
    U->>D: "item f2a3b4c5-..., defectuoso"
    D->>G: ainvoke({messages: [Human("item f2a3...")]})
    G->>CP: Restaurar estado
    G->>T: triage_agent(state) con 5 messages
    T->>T: LLM extrae: items=✅
    T-->>G: {items_to_return: [...], reason: "defectuoso"}
    G->>G: route_after_triage → fetch_order_data ✅
    G->>MCP: get_order_details(order_id)
    MCP-->>G: datos del pedido + cliente
    G->>G: route_after_fetch → evaluator
    G->>G: evaluator → resolver/reject
    G->>CP: Guardar estado final
    G-->>D: result
    D-->>U: "Tu devolución ha sido procesada..."
```

## Detalle de cada nodo

| Nodo | Archivo | Qué hace | Usa MCP |
|------|---------|----------|---------|
| `triage` | `nodes/triage.py` | LLM extrae info del cliente conversacionalmente | ❌ |
| `fetch_order_data` | `nodes/triage.py` | Consulta pedido y historial en Supabase | ✅ supabase:8001 |
| `evaluator` | `nodes/evaluator.py` | RAG sobre políticas + verificación de plazos | ✅ supabase:8001 |
| `resolver` | `nodes/resolution.py` | Crea devolución, genera etiqueta, notifica | ✅ ambos |
| `reject` | `nodes/resolution.py` | Genera mensaje empático de rechazo | ❌ |
| `hitl_admin` | `nodes/resolution.py` | Pausa para aprobación humana (>100€) | ❌ |

## Rol del Checkpointer

```mermaid
graph LR
    T1[Turno 1<br/>ainvoke] -->|guarda| CP[(Checkpointer<br/>PostgreSQL)]
    CP -->|restaura| T2[Turno 2<br/>ainvoke]
    T2 -->|guarda| CP
    CP -->|restaura| T3[Turno 3<br/>ainvoke]
```

- **Entre nodos** (mismo turno): estado compartido en memoria
- **Entre turnos** (distintos ainvoke): estado persistido via checkpointer
- **Identificador**: `thread_id` en `config["configurable"]`
