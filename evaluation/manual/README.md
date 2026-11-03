# 🧪 QA Manual — ReFlow Chatbot de Devoluciones

Kit de pruebas **100% manual**: un humano escribe mensajes en el chat de Streamlit
(http://localhost:8501) y comprueba a ojo que la respuesta del bot es la esperada,
usando 24 casos curados a mano. No hay ningún script que ejecute esto por ti —
para la evaluación automática con LLM real y Langfuse, ver
[`../golden/README.md`](../golden/README.md).

Cubre los tres tipos de resultado que el sistema debe distinguir:

| Símbolo | Resultado | Descripción |
|---------|-----------|-------------|
| ✅ | **VÁLIDO** | Devolución aprobada automáticamente |
| ❌ | **INVÁLIDO** | Devolución rechazada automáticamente |
| 🔄 | **HITL** | Derivada a revisión humana |

---

## 📁 Estructura

```
evaluation/manual/
├── README.md                          ← Este documento (leer primero)
├── cases/
│   ├── qa_manual_testing_cases_v2.csv ← 24 casos curados — fuente de verdad
│   └── qa_manual_testing_cases_v2.xlsx← Excel con colores para pruebas manuales
├── sql/
│   ├── 00_reset_and_seed_complete.sql ← Reset total + carga todo desde cero
│   ├── 01_seed_qa_cases.sql           ← Seed de los 24 casos (aditivo, idempotente)
│   └── 02_seed_pedidos_mixtos.sql     ← Seed de pedidos con varias categorías
└── scripts/
    ├── create_qa_testing_excel.py     ← Regenera el Excel desde el CSV
    └── generate_mixed_qa_kit.py       ← Genera el kit de pedidos mixtos
```

---

## 🚀 Pasos para Ejecutar QA (5 pasos)

### Paso 1 — Levantar la aplicación

Asegúrate de que el backend y el frontend están corriendo:

```bash
# Desde la raíz del proyecto
./deploy.sh local            # Mac/Linux
# ./scripts/start_win.sh     # Windows (Git Bash)
```

O manualmente:

```bash
# Terminal 1 — Backend FastAPI
source .venv/bin/activate
uvicorn backend.api.main:app --reload --port 8000

# Terminal 2 — Frontend Streamlit
source .venv/bin/activate
streamlit run frontend/Chat.py
```

### Paso 2 — Cargar los datos de prueba en Supabase

**Opción A — Reset completo (recomendado para primera vez):**

```bash
# Borra todo y recarga políticas + 24 clientes + 24 productos + 24 pedidos
psql -h <host> -U postgres -d <db> -f evaluation/manual/sql/00_reset_and_seed_complete.sql
```

**Opción B — Solo añadir los 24 casos (sin borrar nada):**

```bash
# Aditivo e idempotente: se puede ejecutar múltiples veces sin duplicar datos
psql -h <host> -U postgres -d <db> -f evaluation/manual/sql/01_seed_qa_cases.sql
```

**Opción C — Desde el SQL Editor web de Supabase:**

1. Abre https://app.supabase.com → tu proyecto
2. SQL Editor → New Query
3. Pega el contenido del fichero SQL elegido
4. Run

> ⚠️ Los scripts SQL **NO insertan `return_requests` ni `return_items`**.  
> Esos los crea el agente al procesar la conversación en el chat — es exactamente lo que se quiere probar.

### Paso 3 — Abrir el Excel de casos

```bash
open evaluation/manual/cases/qa_manual_testing_cases_v2.xlsx
```

El Excel tiene dos pestañas:
- **"Casos de Prueba QA"**: 24 filas coloreadas (🟢 válido / 🟠 inválido / 🟡 HITL)
- **"Leyenda y Guía"**: criterios y definiciones

### Paso 4 — Ejecutar cada caso en el chat

Para cada fila del Excel:

1. Abre el chat en http://localhost:8501
2. Escribe el **Saludo** de la columna J
3. Cuando el bot pida el pedido, escribe el **Mensaje** de la columna K
4. Verifica que la respuesta contiene las **Keywords** de la columna L
5. Comprueba los **Criterios** de la columna M

**Ejemplo con QA-001 (✅ VÁLIDO):**
```
Tú:  "Hola, tengo un problema con mi pedido"
Bot: "¿Me indicas el número de tu pedido?"
Tú:  "Es el pedido ORD-QA-0001. El alimento llegó defectuoso, empaque dañado"
Bot: → Debe decir "aprobada, 29.99€, dentro de plazo, defectuoso"
```

### Paso 5 — Registrar resultado

Escribe ✓ o ✗ en el Excel según si el bot respondió correctamente.

---

## 📊 Los 24 Casos de Prueba

| ID | Tipo | Categoría | Motivo | Días/Plazo | Importe | Resultado Esperado |
|----|------|-----------|--------|------------|---------|-------------------|
| QA-001 | ✅ VÁLIDO | Alimentación | Defectuoso | 5/14 | 29.99€ | Aprobada automáticamente |
| QA-002 | 🔄 HITL | Bebé | Defectuoso | 7/30 | 299.99€ | HITL — importe > 100€ |
| QA-003 | ✅ VÁLIDO | Calzado | Talla incorrecta | 12/30 | 79.99€ | Aprobada automáticamente |
| QA-004 | ❌ INVÁLIDO | Cosmética | Cambio de opinión | 0/21 | 49.99€ | Rechazada — Art. 103 higiene |
| QA-005 | 🔄 HITL | Deportes | Defectuoso | 17/30 | 399.99€ | HITL — importe > 100€ |
| QA-006 | ❌ INVÁLIDO | Droguería | Producto usado | 25/21 | 12.99€ | Rechazada — Art. 103 higiene |
| QA-007 | ❌ INVÁLIDO | Libros | Cambio de opinión | 42/21 | 24.99€ | Rechazada — fuera de plazo |
| QA-008 | ✅ VÁLIDO | Mascotas | Defectuoso | 3/21 | 39.99€ | Aprobada automáticamente |
| QA-009 | 🔄 HITL | Electrodomésticos | Defectuoso | 9/30 | 849.99€ | HITL — importe > 100€ |
| QA-010 | 🔄 HITL | Electrónica | Faltan piezas | 15/30 | 899.99€ | HITL — importe > 100€ |
| QA-011 | ✅ VÁLIDO | Jardinería | Artículo equivocado | 4/30 | 69.99€ | Aprobada automáticamente |
| QA-012 | ✅ VÁLIDO | Juguetes | Defectuoso | 19/30 | 89.99€ | Aprobada automáticamente |
| QA-013 | ✅ VÁLIDO | Moda | Talla incorrecta | 0/30 | 34.99€ | Aprobada automáticamente |
| QA-014 | 🔄 HITL | Muebles | Defectuoso | 2/14 | 1299.99€ | HITL — importe > 100€ + cliente frecuente ⚠️ |
| QA-015 | ✅ VÁLIDO | Hogar | Defectuoso | 8/30 | 59.99€ | Aprobada automáticamente |
| QA-016 | ❌ INVÁLIDO | Joyería | Defectuoso | 29/15 | 89.99€ | Rechazada — fuera de plazo |
| QA-017 | ❌ INVÁLIDO | Alimentación | Artículo equivocado | 16/14 | 34.99€ | Rechazada — fuera de plazo |
| QA-018 | 🔄 HITL | Electrodomésticos | Defectuoso | 24/30 | 549.99€ | HITL — importe > 100€ |
| QA-019 | 🔄 HITL | Calzado | Talla incorrecta | 25/30 | 119.99€ | HITL — importe > 100€ |
| QA-020 | 🔄 HITL | Bebé | Defectuoso | 6/30 | 199.99€ | HITL — importe > 100€ + equipo seguridad |
| QA-021 | ⚠️ AMBIGUO | Droguería | Defectuoso | 10/21 | 18.99€ | Depende de si está abierto |
| QA-022 | ✅ VÁLIDO | Alimentación | Defectuoso | 5/14 | 59.99€ | Aprobada automáticamente |
| QA-023 | ❌ INVÁLIDO | Cosmética | Cambio de opinión | 8/21 | 39.99€ | Rechazada — Art. 103 higiene |
| QA-024 | 🔄 HITL | Electrónica | Defectuoso | 23/30 | 129.99€ | HITL — importe > 100€ |

**Resumen:** ✅ 8 válidos · ❌ 6 inválidos · 🔄 9 HITL · ⚠️ 1 ambiguo

---

## 🎯 Reglas de Negocio que se Prueban

### 1. Plazo de devolución (varía por categoría)

| Categoría | Plazo |
|-----------|-------|
| Alimentación | 14 días |
| Joyería | 15 días |
| Muebles | 14 días |
| Cosmética / Droguería / Mascotas / Libros | 21 días |
| Resto de categorías | 30 días |

Casos que prueban plazo superado: **QA-007** (42 vs 21), **QA-016** (29 vs 15), **QA-017** (16 vs 14).

### 2. Umbral de 100€ → HITL automático

Importe > 100€ activa **siempre** revisión humana, incluso si el resto de criterios son válidos.  
Ejemplo: QA-019 (botas 119.99€, talla válida → HITL igual).

### 3. Exclusiones legales — Art. 103 TRLGDCU

Productos de higiene (cosmética, droguería, mascotas, alimentación, bebé) con embalaje abierto → **rechazo automático**, sin importar el plazo.  
Casos: **QA-004, QA-006, QA-023**.

### 4. Cliente frecuente

Clientes `cust-14` y `cust-21` están marcados como devolutores frecuentes.  
El agente debe detectar el patrón y escalar a HITL.  
Caso: **QA-014** (sofá 1299€ + cliente frecuente).

### 5. Recargos de reposición

| Categoría | Recargo |
|-----------|---------|
| Electrónica | 15% |
| Electrodomésticos | 10% |
| Muebles | 15% |
| Resto | 0-5% |

### 6. Pedidos mixtos (varias categorías)

Cubiertos por `02_seed_pedidos_mixtos.sql`: prueba que el agente evalúa la elegibilidad por artículo individual, no por pedido completo.

---

## ✅ Checklist de Validación por Caso

Para cada caso marca si el bot:

- [ ] Identifica correctamente el número de pedido
- [ ] Consulta la política de la categoría correcta
- [ ] Calcula correctamente los días desde la entrega
- [ ] Verifica el estado del artículo (`unopened`, `defective`, etc.)
- [ ] Aplica la regla de plazo (dentro / fuera / zona frontera)
- [ ] Detecta importe > 100€ y activa HITL si aplica
- [ ] Aplica exclusiones legales Art. 103 para productos de higiene
- [ ] Identifica cliente frecuente y aplica reglas de abuso
- [ ] Emite el veredicto correcto (Aprobación / Rechazo / HITL)
- [ ] Indica el importe de reembolso exacto (con recargos si aplica)

---

## 🐛 Troubleshooting

**El bot no reconoce el número de pedido**
→ Verifica que el seed SQL se ejecutó correctamente. Comprueba en Supabase que existen filas en `orders` con `order_number` como `ORD-QA-0001`.

**El bot rechaza algo que debería aprobar**
→ Revisa los criterios de la columna M del Excel. Verifica que el `allowed_conditions` de `return_policies` incluye el estado del artículo.

**El bot no activa HITL cuando debería**
→ Confirma que el importe del pedido es > 100€. Revisa si el cliente está marcado como frecuente (`is_frequent_returner = true`).

**El bot aprueba algo de higiene que debería rechazar**
→ Comprueba que el nodo `policy_rules` tiene la lógica del Art. 103. Ver `backend/agents/nodes/`.

**Error al ejecutar el SQL**
→ Asegúrate de haber ejecutado primero las migraciones: `supabase/migrations/001_*.sql` … `013_*.sql`.

---

## 🔄 Regenerar el Excel

Si modificas `qa_manual_testing_cases_v2.csv`, regenera el Excel con:

```bash
source .venv/bin/activate
python evaluation/manual/scripts/create_qa_testing_excel.py
```

---

*Generado: 2026-08-16 · Dataset v2 · 24 casos QA manuales · Compatible con ReFlow schema v1.13*
