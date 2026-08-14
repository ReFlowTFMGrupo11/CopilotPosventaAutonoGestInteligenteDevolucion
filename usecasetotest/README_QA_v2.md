# 🧪 QA Manual Testing Dataset v2

**Dataset de pruebas completo para validación end-to-end del chatbot de devoluciones autónomo.**

24 casos de prueba cubriendo: ✅ VÁLIDO | ❌ INVÁLIDO | 🔄 REVISIÓN HUMANA

---

## 📦 Archivos Incluidos

### 1. **`qa_manual_testing_seed_v2.sql`**
Script SQL **aditivo e idempotente** que carga:
- **16 categorías** de productos con sus políticas de devolución
- **24 clientes** (2 marcados como "frecuentes" para detección de abuso)
- **24 productos** (1 por caso de prueba)
- **24 pedidos** ya entregados (con fechas variables)
- **24 líneas de pedido** (order_items)

**NO inserta `return_requests/return_items`**: esos deben crearlos los agentes al procesar el chat.

### 2. **`qa_manual_testing_cases_v2.csv`**
Tabla con 24 filas (una por caso):
- Nº pedido exacto a usar
- Saludo inicial para el chat
- Mensaje con datos del pedido
- Palabras clave esperadas en la respuesta
- Criterios de validación específicos

### 3. **`qa_manual_testing_cases_v2.xlsx`**
Excel profesional con **2 pestañas**:

**Pestaña "Casos de Prueba QA":**
- 24 filas con todos los casos
- Coloreadas: 🟢 Verde (VÁLIDO) | 🟠 Naranja (INVÁLIDO) | 🟡 Amarillo (HITL)
- Columnas: ID | Resultado | Nº Pedido | Categoría | Producto | Motivo | Plazo | Días | Importe | Saludo | Mensaje | Keywords | Criterios | Notas

**Pestaña "Leyenda y Guía":**
- Instrucciones paso a paso
- Definición de cada tipo de resultado
- Criterios de aprobación/rechazo/HITL
- Notas sobre categorías sensibles

---

## 🚀 QUICKSTART (5 Pasos)

### Paso 1: Cargar datos en Supabase
```bash
# Opción A: Desde psql
psql -h <host> -U postgres -d <db> -f qa_manual_testing_seed_v2.sql

# Opción B: Desde SQL Editor web de Supabase
# 1. Abre https://app.supabase.com
# 2. SQL Editor → New Query
# 3. Pega contenido de qa_manual_testing_seed_v2.sql
# 4. Run
```

### Paso 2: Abre el Excel
```bash
# Windows
start qa_manual_testing_cases_v2.xlsx

# Mac/Linux
open qa_manual_testing_cases_v2.xlsx
```

### Paso 3: Para cada caso, en el chat:
```
Cliente: [Copia "Saludo del Chat" de columna J]
Bot: "¿Me indicas el número de tu pedido?"
Cliente: [Copia "Mensaje con Nº Pedido" de columna K]
Bot: [Verifica que contenga "Palabras Clave Esperadas" de columna L]
```

### Paso 4: Valida criterios
Revisa los criterios de la columna M y verifica que se cumplan.

### Paso 5: Marca resultado
Escribe ✓ o ✗ en el Excel.

---

## 📊 Matriz de los 24 Casos

### Casos VÁLIDOS (Aprobación Automática) ✅
| ID | Categoría | Producto | Motivo | Plazo | Días | Importe | Resultado |
|---|---|---|---|---|---|---|---|
| QA-001 | Alimentación | Alimento | defective | 14 | 5 | 29.99€ | ✅ Aprobada |
| QA-003 | Calzado | Zapatillas | wrong_size | 30 | 12 | 79.99€ | ✅ Aprobada |
| QA-008 | Mascotas | Comida | defective | 21 | 3 | 39.99€ | ✅ Aprobada |
| QA-011 | Jardinería | Herramientas | wrong_item | 30 | 4 | 69.99€ | ✅ Aprobada |
| QA-012 | Juguetes | Juguete | defective | 30 | 19 | 89.99€ | ✅ Aprobada |
| QA-013 | Moda | Camiseta | wrong_size | 30 | 0 | 34.99€ | ✅ Aprobada |
| QA-015 | Hogar | Lámpara | defective | 30 | 8 | 59.99€ | ✅ Aprobada |
| QA-022 | Alimentación | Aceite gourmet | defective | 14 | 5 | 59.99€ | ✅ Aprobada |

**Criterios:** Dentro de plazo + Estado permitido + Importe ≤ 100€ + Sin motivos sensibles

---

### Casos INVÁLIDOS (Rechazo Automático) ❌
| ID | Categoría | Producto | Motivo | Plazo | Días | Razón Rechazo |
|---|---|---|---|---|---|---|
| QA-004 | Cosmética | Perfume | changed_mind | 21 | 0 | Art. 103: higiene sensible + abierto |
| QA-006 | Droguería | Champú | changed_mind | 21 | 25 | Art. 103: higiene sensible + usado |
| QA-007 | Libros | Libro | changed_mind | 21 | 42 | **FUERA DE PLAZO** (42 vs 21) |
| QA-016 | Joyería | Reloj | defective | 15 | 29 | **FUERA DE PLAZO** (29 vs 15) |
| QA-017 | Alimentación | Aceite | wrong_item | 14 | 16 | **FUERA DE PLAZO** (16 vs 14) |
| QA-023 | Cosmética | Esmalte | changed_mind | 21 | 8 | Art. 103: higiene sensible + abierto |

**Criterios:** Plazo superado (>5-10 días) | Exclusión legal (Art. 103) | Estado no permitido

---

### Casos REVISIÓN HUMANA (HITL) 🔄
| ID | Categoría | Producto | Motivo | Plazo | Días | Importe | Razón HITL |
|---|---|---|---|---|---|---|---|
| QA-002 | Bebé | Cochecito | defective | 30 | 7 | 299.99€ | **Importe > 100€** |
| QA-005 | Deportes | Bicicleta | defective | 30 | 17 | 399.99€ | **Importe > 100€** |
| QA-009 | Electrodomésticos | Nevera | defective | 30 | 9 | 849.99€ | **Importe > 100€** |
| QA-010 | Electrónica | Portátil | missing_parts | 30 | 15 | 899.99€ | **Importe > 100€** |
| QA-014 | Muebles | Sofá | defective | 14 | 2 | 1299.99€ | **Importe > 100€ + Cliente frecuente ⚠️** |
| QA-018 | Electrodomésticos | Lavadora | defective | 30 | 24 | 549.99€ | **Importe > 100€** |
| QA-019 | Calzado | Botas | wrong_size | 30 | 25 | 119.99€ | **Importe > 100€** (aunque talla es válida) |
| QA-020 | Bebé | Silla coche | defective | 30 | 6 | 199.99€ | **Importe > 100€ + Seguridad bebé** |
| QA-024 | Electrónica | Teclado | defective | 30 | 23 | 129.99€ | **Importe > 100€** |

**Criterios:** Importe > 100€ (umbral fijo) | Zona frontera de plazo (±2 a ±5 días) | Motivo sensible (alergia, falsificación) | Cliente frecuente | Falta de evidencia

**⚠️ NOTA ESPECIAL:** QA-021 (Loción droguería) es ambiguo: aprobación o rechazo depende de si está abierta o sin abrir.

---

## 🎯 Qué Prueba Cada Caso

### Reglas de Plazo:
- **QA-001, 003, 008, 011, 012, 013, 015, 022**: Dentro de plazo ✓
- **QA-007**: Fuera de plazo libro (42 vs 21)
- **QA-016**: Fuera de plazo joyería (29 vs 15 - plazo muy corto)
- **QA-017**: Fuera de plazo alimentación (16 vs 14)

### Reglas de Importe:
- **QA-001, 003, 008, 011, 012, 013, 015, 022**: < 100€ = Aprobación automática
- **QA-002, 005, 009, 010, 014, 018, 019, 020, 024**: ≥ 100€ = HITL obligatorio

### Reglas de Higiene (Art. 103 TRLGDCU):
- **QA-004, 006, 023**: Cosmética/Droguería + cambio opinión + abierto = Rechazo legal
- **QA-021**: Droguería (ambiguo: depende de si abierta)

### Cliente Frecuente:
- **QA-014** (cust-14): Sofá caro + cliente frecuente = HITL por abuso
- **QA-21** (cust-21): Cliente frecuente pero comida barata

### Categorías Especiales:
- **Joyería (QA-016)**: Plazo MUY corto (15 días)
- **Muebles (QA-014)**: Plazo corto (14 días) + recargo 15% si usado
- **Moda (QA-013)**: Sin penalización por talla
- **Bebé (QA-020)**: Equipo de seguridad

---

## 📝 Estructura de los Datos SQL

### Tabla `return_policies`
```sql
category | max_return_days | requires_original_packaging | restocking_fee_percent | allowed_conditions
```
- **alimentacion**: 14 días
- **bebe_puericultura**: 30 días
- **calzado**: 30 días
- **cosmetica_perfumeria**: 21 días ⚠️ (higiene sensible)
- **drogueria_salud**: 21 días ⚠️ (higiene sensible)
- **electrodomesticos**: 30 días, recargo 10%
- **electronica_informatica**: 30 días, recargo 15%
- **joyeria_relojes**: 15 días (corto)
- **libros_papeleria**: 21 días
- **mascotas**: 21 días ⚠️ (higiene sensible)
- **moda_ropa**: 30 días, sin recargo por talla
- **muebles**: 14 días (corto), recargo 15%
- Etc.

---

## ✅ Checklist de Validación

Para cada caso, verifica:

- [ ] El bot **identifica correctamente** el nº de pedido
- [ ] El bot **consulta la política** de la categoría correcta
- [ ] El bot **calcula correctamente** los días desde entrega
- [ ] El bot **verifica el estado** del artículo (unopened, defective, etc.)
- [ ] El bot **aplica la regla de plazo** (dentro/fuera/frontera)
- [ ] El bot **detecta importe > 100€** y activa HITL si aplica
- [ ] El bot **aplica exclusiones legales** (Art. 103 para higiene)
- [ ] El bot **identifica cliente frecuente** y aplica reglas de abuso
- [ ] El bot **emite veredicto correcto**: Aprobación/Rechazo/HITL
- [ ] El bot **indica reembolso exacto** (con recargos si aplica)

---

## 🔍 Notas Importantes

### 1. **Categorías Sensibles (Higiene)**
Cosmética, Droguería, Mascotas, Alimentación, Bebé.
- **Regla**: Art. 103 TRLGDCU prohíbe devolución si embalaje está roto
- **Operativamente**: Si está "abierto" o "usado" → Rechazo automático, independientemente del plazo

### 2. **Clientes Frecuentes**
- **cust-14** (QA-014): Sofá muy caro, cliente marcado como "frecuente"
- **cust-21** (QA-21): Otra cliente frecuente
- **Uso**: Prueba que el bot detecta patrones de abuso/devoluciones excesivas

### 3. **Umbral de 100€**
- **Fijo**: Importe > 100€ SIEMPRE activa HITL, incluso si es válido por otros criterios
- Ejemplos: QA-019 (botas 119.99€, aunque talla es válida = HITL)

### 4. **Zona Frontera**
- Plazo entre ±2 a ±5 días del máximo = HITL (incluso si es válido)
- Ejemplo: Si max=30 días, plazo 28-29 días = HITL

### 5. **Recargo de Reposición**
- Moda: 0%
- Electrónica: 15%
- Electrodomésticos: 10%
- Muebles: 15%
- Otros: 0-5%

---

## 🐛 Si algo Falla

### El bot no reconoce el nº de pedido
- Verifica que el pedido existe en Supabase
- Ejecuta el SQL de seed y confirma que se insertaron 24 órdenes

### El bot rechaza algo que debería aprobar
- Revisa los criterios de la columna M
- Verifica que la categoría está en las políticas de devolución
- Comprueba que el estado ('unopened', 'defective', etc.) está en `allowed_conditions`

### El bot no activa HITL cuando debería
- Verifica que el importe es > 100€
- Revisa que el cliente está marcado como frecuente (si aplica)
- Comprueba si está en zona frontera de plazo

---

## 📋 Resumen Rápido

| Tipo | Cantidad | Criterios |
|---|---|---|
| ✅ VÁLIDO | 8 casos | Plazo OK + Estado OK + Importe ≤ 100€ |
| ❌ INVÁLIDO | 6 casos | Plazo superado O exclusión legal |
| 🔄 HITL | 9 casos | Importe > 100€ (principalmente) |
| ⚠️ Ambiguo | 1 caso | QA-021: depende de si está abierto |

**Total: 24 casos de prueba listos para usar**

---

**Generado:** 2026-08-11  
**Versión:** v2 (basado en qa_manual_testing_seed.sql original)  
**Compatibilidad:** Supabase migrations + ReFlow schema  
**Formato:** SQL (seed) + CSV + XLSX (profesional)
