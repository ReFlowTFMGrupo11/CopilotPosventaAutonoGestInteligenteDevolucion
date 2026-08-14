# 📑 Índice - Carpeta `usecasetotest`

## 📦 Archivos en esta Carpeta

### 🗂️ Estructura
```
usecasetotest/
├── qa_manual_testing_seed_v2.sql          ← Script SQL (carga 24 casos)
├── qa_manual_testing_cases_v2.csv         ← Casos en CSV (importable)
├── qa_manual_testing_cases_v2.xlsx        ← Excel profesional (instrucciones + casos)
├── create_qa_testing_excel.py             ← Script generador del Excel
├── README_QA_v2.md                        ← Guía COMPLETA (leer esto)
└── INDEX.md                               ← Este archivo
```

---

## 🎯 Por dónde Empezar

### Opción 1: Quiero empezar AHORA (5 min)
1. Lee **"Guía Rápida"** abajo
2. Ejecuta `qa_manual_testing_seed_v2.sql` en Supabase
3. Abre `qa_manual_testing_cases_v2.xlsx`
4. Empieza a probar

### Opción 2: Quiero entender TODO
1. Lee **`README_QA_v2.md`** completo
2. Luego sigue Opción 1

### Opción 3: Prefiero CSV
1. Abre **`qa_manual_testing_cases_v2.csv`** en Excel o Google Sheets
2. Importa los datos
3. Prueba manualmente

---

## ⚡ Guía Rápida (5 minutos)

### Paso 1: Carga SQL (1 min)
```bash
psql -h tu-host -U postgres -d tu-db -f qa_manual_testing_seed_v2.sql
```

### Paso 2: Abre el Excel (30 seg)
```
Doble-clic: qa_manual_testing_cases_v2.xlsx
```

### Paso 3: Prueba UN caso (2 min)
- Línea 2: QA-001 (VÁLIDO)
- Copia del Excel columna J: `"Hola, tengo un problema"`
- Pega en chat del bot
- Copia columna K: `"Es el pedido ORD-QA-0001. El alimento llegó defectuoso"`
- Pega en chat
- Bot debería decir: `"aprobada, 29.99€"`

### Paso 4: Repite para los 24 casos
Marca ✓ o ✗ en el Excel según el resultado.

---

## 📊 Lo que hay dentro

### `qa_manual_testing_seed_v2.sql` (Script SQL)
**380 líneas** que insertan:
- 16 categorías con políticas de devolución
- 24 clientes (2 frecuentes)
- 24 productos
- 24 pedidos (YA ENTREGADOS)
- 24 líneas de pedido

**Estructura**: Usa `ON CONFLICT DO NOTHING` (puede ejecutarse múltiples veces sin problemas)

**Qué NO hace**: No inserta `return_requests` ni `return_items` (esos los crea el bot al chat)

---

### `qa_manual_testing_cases_v2.xlsx` (Excel)
**2 pestañas:**

#### Pestaña "Casos de Prueba QA"
- 24 casos con colores:
  - 🟢 Verde: VÁLIDO (aprobación automática)
  - 🟠 Naranja: INVÁLIDO (rechazo automático)
  - 🟡 Amarillo: REVISIÓN HUMANA (derivar a agente)
- Columnas A-N con todos los detalles

#### Pestaña "Leyenda y Guía"
- Instrucciones paso a paso
- Criterios de cada tipo
- Notas importantes

**Tamaño**: ~50 KB, fácil de compartir

---

### `qa_manual_testing_cases_v2.csv`
Versión CSV de los 24 casos (importable a Google Sheets, Airtable, etc.)

**Columnas:**
- case_id | tipo_resultado | orden_numero | order_id | order_item_id | customer_email | categoria | producto | motivo_esperado | plazo_max | dias_desde_entrega | importe | saludo_chat | mensaje_chat | respuesta_esperada_keywords | criterios_validacion | notas_prueba

---

### `README_QA_v2.md` (Documentación completa)
**3.500 palabras** cubriendo:
- Estructura del dataset
- Quickstart (5 pasos)
- Matriz de los 24 casos
- Criterios de validación
- Troubleshooting
- Reglas especiales (higiene, importe >100€, etc.)

**Recomendación**: Lee esto si hay dudas.

---

## 🎯 Los 24 Casos Resumidos

| # | ID | Tipo | Categoría | Motivo | Resultado Esperado |
|---|---|---|---|---|---|
| 1 | QA-001 | ✅ VÁLIDO | Alimentación | Defectuoso | Aprobada |
| 2 | QA-002 | 🔄 HITL | Bebé | Defectuoso | HITL (299€) |
| 3 | QA-003 | ✅ VÁLIDO | Calzado | Talla | Aprobada |
| 4 | QA-004 | ❌ INVÁLIDO | Cosmética | Cambio opinión | Rechazada (higiene) |
| 5 | QA-005 | 🔄 HITL | Deportes | Defectuoso | HITL (399€) |
| 6 | QA-006 | ❌ INVÁLIDO | Droguería | Usado | Rechazada (higiene) |
| 7 | QA-007 | ❌ INVÁLIDO | Libros | Cambio opinión | Rechazada (plazo 42 vs 21) |
| 8 | QA-008 | ✅ VÁLIDO | Mascotas | Defectuoso | Aprobada |
| 9 | QA-009 | 🔄 HITL | Electrodomésticos | Defectuoso | HITL (849€) |
| 10 | QA-010 | 🔄 HITL | Electrónica | Falta pieza | HITL (899€) |
| 11 | QA-011 | ✅ VÁLIDO | Jardinería | Equivocado | Aprobada |
| 12 | QA-012 | ✅ VÁLIDO | Juguetes | Roto | Aprobada |
| 13 | QA-013 | ✅ VÁLIDO | Moda | Talla | Aprobada |
| 14 | QA-014 | 🔄 HITL | Muebles | Defectuoso | HITL (1299€ + cliente frecuente) |
| 15 | QA-015 | ✅ VÁLIDO | Hogar | Defectuoso | Aprobada |
| 16 | QA-016 | ❌ INVÁLIDO | Joyería | Defectuoso | Rechazada (plazo 29 vs 15) |
| 17 | QA-017 | ❌ INVÁLIDO | Alimentación | Equivocado | Rechazada (plazo 16 vs 14) |
| 18 | QA-018 | 🔄 HITL | Electrodomésticos | Defectuoso | HITL (549€) |
| 19 | QA-019 | 🔄 HITL | Calzado | Talla | HITL (119€) |
| 20 | QA-020 | 🔄 HITL | Bebé | Defectuoso | HITL (199€ + seguridad) |
| 21 | QA-021 | ⚠️ AMBIGUO | Droguería | Defectuoso | Depende si abierto |
| 22 | QA-022 | ✅ VÁLIDO | Alimentación | Fermentado | Aprobada |
| 23 | QA-023 | ❌ INVÁLIDO | Cosmética | Cambio opinión | Rechazada (higiene) |
| 24 | QA-024 | 🔄 HITL | Electrónica | Teclas rotas | HITL (129€) |

**Resumen:**
- ✅ VÁLIDO: 8 casos
- ❌ INVÁLIDO: 6 casos
- 🔄 HITL: 9 casos
- ⚠️ AMBIGUO: 1 caso

---

## 🔑 Conceptos Clave

### ✅ VÁLIDO
Debe APROBAR automáticamente:
- Dentro de plazo ✓
- Estado permitido ✓
- Importe ≤ 100€ ✓
- Sin motivos sensibles ✓

### ❌ INVÁLIDO
Debe RECHAZAR automáticamente:
- Fuera de plazo (>5-10 días extra)
- Exclusión legal (Art. 103 higiene)
- Estado no permitido

### 🔄 REVISIÓN HUMANA (HITL)
Debe DERIVAR a agente humano:
- Importe > 100€ (umbral fijo)
- Zona frontera plazo (±2 a ±5 días)
- Motivo sensible (alergia, falsificación)
- Cliente frecuente
- Falta de evidencia

---

## ❓ FAQ Rápido

**P: ¿Por dónde empiezo?**  
R: Lee "Guía Rápida" arriba (5 min)

**P: ¿Qué es "cliente frecuente"?**  
R: cust-14 y cust-21. El bot debe detectar patrón de devoluciones y aplicar reglas de abuso.

**P: ¿Por qué hay 9 HITL?**  
R: Principalmente por importe > 100€. El umbral de 100€ SIEMPRE activa HITL automáticamente.

**P: ¿Qué es Art. 103 TRLGDCU?**  
R: Ley española que prohíbe devolución de productos de higiene si están abiertos/usados.

**P: ¿Qué pasa si falla un caso?**  
R: Lee la sección "Si algo Falla" en README_QA_v2.md

**P: ¿Puedo ejecutar el SQL múltiples veces?**  
R: Sí, usa `ON CONFLICT DO NOTHING`. No duplica datos.

**P: ¿Debo crear return_requests manualmente?**  
R: No, el bot los crea al procesar el chat. El SQL SOLO carga customers, products, orders, order_items, policies.

---

## 📞 Contacto / Notas

**Dataset creado:** 2026-08-11  
**Basado en:** `qa_manual_testing_seed.sql` original + `reset_and_seed_qa.sql`  
**Casos:** 24 (cubriendo VALID / INVALID / HUMAN_REVIEW)  
**Categorías:** 16 (todas las del catálogo ReFlow)  
**Reglas probadas:**  
- ✓ Plazo de devolución (varía por categoría: 14-30 días)
- ✓ Importe > 100€ (HITL automático)
- ✓ Zona frontera de plazo
- ✓ Exclusiones legales (Art. 103 higiene)
- ✓ Cliente frecuente (detección de abuso)
- ✓ Estados permitidos vs prohibidos
- ✓ Recargos de reposición

---

**Listo para usar. Adelante! 🚀**
