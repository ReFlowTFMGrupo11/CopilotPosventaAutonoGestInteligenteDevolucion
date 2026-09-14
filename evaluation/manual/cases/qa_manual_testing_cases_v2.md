# 🧪 QA Manual Testing — 24 Casos de Prueba v2

**Fecha:** 2026-08-18 · **Rama:** `tamara-testing-v2`  
**BD requerida:** ejecutar `evaluation/manual/sql/00_reset_and_seed_complete.sql` en Supabase antes de probar.

---

## Leyenda

| Símbolo | Resultado esperado |
|---------|-------------------|
| ✅ | **VÁLIDO** — Bot aprueba automáticamente |
| ❌ | **INVÁLIDO** — Bot rechaza automáticamente |
| 🔄 | **HITL** — Bot deriva a revisión humana |
| ⚠️ | **AMBIGUO** — Depende del contexto |

**Columnas de resultado para rellenar al probar:**
- **✓/✗** — Si el bot respondió correctamente
- **Observaciones** — Notas sobre la respuesta real del bot

---

## Casos VÁLIDOS ✅ — Aprobación automática

### QA-001 · Alimentación · Defectuoso
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0001` |
| **Categoría** | alimentacion |
| **Producto** | Alimento |
| **Motivo** | defective |
| **Plazo máx.** | 14 días |
| **Días desde entrega** | 5 |
| **Importe** | 29.99 € |
| **Saludo chat** | `Hola, tengo un problema con mi pedido` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0001. El alimento llegó defectuoso, empaque dañado` |
| **Keywords esperadas** | aprobada, 29.99€, dentro de plazo, defectuoso |
| **Criterios** | Plazo OK (5/14) · Estado válido · Importe < 100€ |
| **Resultado** | |
| **Observaciones** | |

---

### QA-003 · Calzado · Talla incorrecta
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0003` |
| **Categoría** | calzado |
| **Producto** | Zapatillas |
| **Motivo** | wrong_size |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 12 |
| **Importe** | 79.99 € |
| **Saludo chat** | `Quiero cambiar un artículo` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0003. Las zapatillas me quedan pequeñas` |
| **Keywords esperadas** | aprobada, cambio sin recargo, 79.99€ |
| **Criterios** | Calzado: talla equivocada sin penalización |
| **Resultado** | |
| **Observaciones** | |

---

### QA-008 · Mascotas · Defectuoso
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0008` |
| **Categoría** | mascotas |
| **Producto** | Comida mascotas |
| **Motivo** | defective |
| **Plazo máx.** | 21 días |
| **Días desde entrega** | 3 |
| **Importe** | 39.99 € |
| **Saludo chat** | `Buenos días, tengo un problema` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0008. La comida tiene olor extraño, defectuosa` |
| **Keywords esperadas** | aprobada, defectuoso, 39.99€ |
| **Criterios** | Plazo OK (3/21) · Estado válido · Importe < 100€ |
| **Resultado** | |
| **Observaciones** | |

---

### QA-011 · Jardinería · Artículo equivocado
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0011` |
| **Categoría** | jardineria_bricolaje |
| **Producto** | Herramientas |
| **Motivo** | wrong_item |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 4 |
| **Importe** | 69.99 € |
| **Saludo chat** | `Tengo un problema` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0011. Recibí herramientas equivocadas` |
| **Keywords esperadas** | aprobada, artículo equivocado, 69.99€ |
| **Criterios** | Plazo OK (4/30) · Estado válido · Importe < 100€ |
| **Resultado** | |
| **Observaciones** | |

---

### QA-012 · Juguetes · Defectuoso
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0012` |
| **Categoría** | juguetes |
| **Producto** | Juguete |
| **Motivo** | defective |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 19 |
| **Importe** | 89.99 € |
| **Saludo chat** | `El juguete está roto` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0012. El juguete llegó roto, no funciona` |
| **Keywords esperadas** | aprobada, defectuoso, 89.99€ |
| **Criterios** | Plazo OK (19/30) · Estado válido · Importe < 100€ |
| **Resultado** | |
| **Observaciones** | |

---

### QA-013 · Moda · Talla incorrecta
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0013` |
| **Categoría** | moda_ropa |
| **Producto** | Camiseta |
| **Motivo** | wrong_size |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 0 |
| **Importe** | 34.99 € |
| **Saludo chat** | `Acabo de recibir` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0013. La camiseta es M pero pedí L` |
| **Keywords esperadas** | aprobada, talla incorrecta, sin recargo |
| **Criterios** | Moda: talla equivocada sin penalización |
| **Resultado** | |
| **Observaciones** | |

---

### QA-015 · Hogar · Defectuoso
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0015` |
| **Categoría** | hogar_decoracion |
| **Producto** | Lámpara |
| **Motivo** | defective |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 8 |
| **Importe** | 59.99 € |
| **Saludo chat** | `La lámpara no enciende` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0015. La lámpara no enciende, cable dañado` |
| **Keywords esperadas** | aprobada, defectuoso, 59.99€ |
| **Criterios** | Plazo OK (8/30) · Estado válido · Importe < 100€ |
| **Resultado** | |
| **Observaciones** | |

---

### QA-022 · Alimentación · Defectuoso
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0022` |
| **Categoría** | alimentacion |
| **Producto** | Alimento gourmet |
| **Motivo** | defective |
| **Plazo máx.** | 14 días |
| **Días desde entrega** | 5 |
| **Importe** | 59.99 € |
| **Saludo chat** | `Alimento gourmet` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0022. El alimento llegó en mal estado, fermentado` |
| **Keywords esperadas** | aprobada, defectuoso, 59.99€ |
| **Criterios** | Plazo OK (5/14) · Estado válido · Importe < 100€ |
| **Resultado** | |
| **Observaciones** | |

---

## Casos INVÁLIDOS ❌ — Rechazo automático

### QA-004 · Cosmética · Cambio de opinión (Art. 103 higiene)
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0004` |
| **Categoría** | cosmetica_perfumeria |
| **Producto** | Perfume |
| **Motivo** | changed_mind |
| **Plazo máx.** | 21 días |
| **Días desde entrega** | 0 |
| **Importe** | 49.99 € |
| **Saludo chat** | `Buenos días, tengo un problema` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0004. El perfume no me gusta, cambié opinión` |
| **Keywords esperadas** | rechazado, higiene sensible, Art. 103 |
| **Criterios** | Cosmética + cambio opinión + abierto = rechazo legal |
| **Resultado** | |
| **Observaciones** | |

---

### QA-006 · Droguería · Producto usado (Art. 103 higiene)
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0006` |
| **Categoría** | drogueria_salud |
| **Producto** | Champú |
| **Motivo** | changed_mind |
| **Plazo máx.** | 21 días |
| **Días desde entrega** | 25 ⚠️ también fuera de plazo |
| **Importe** | 12.99 € |
| **Saludo chat** | `Quiero devolver un producto` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0006. El champú no me gustó, lo usé` |
| **Keywords esperadas** | rechazado, higiene sensible, usado |
| **Criterios** | Droguería + usado + cambio opinión |
| **Resultado** | |
| **Observaciones** | |

---

### QA-007 · Libros · Fuera de plazo
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0007` |
| **Categoría** | libros_papeleria |
| **Producto** | Libro |
| **Motivo** | changed_mind |
| **Plazo máx.** | 21 días |
| **Días desde entrega** | 42 🚨 muy fuera de plazo |
| **Importe** | 24.99 € |
| **Saludo chat** | `Hola buenos días` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0007. Cambié de opinión, el libro no lo necesito` |
| **Keywords esperadas** | rechazado, fuera de plazo, 42 vs 21 |
| **Criterios** | Plazo 42 días > 21 máximo |
| **Resultado** | |
| **Observaciones** | |

---

### QA-016 · Joyería · Fuera de plazo (plazo muy corto: 15 días)
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0016` |
| **Categoría** | joyeria_relojes |
| **Producto** | Reloj |
| **Motivo** | defective |
| **Plazo máx.** | 15 días 🚨 plazo muy corto |
| **Días desde entrega** | 29 |
| **Importe** | 299.99 € |
| **Saludo chat** | `Tengo un problema` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0016. El reloj se detiene cada pocas horas` |
| **Keywords esperadas** | rechazado, joyería plazo corto, 29 días supera 15 |
| **Criterios** | Joyería: plazo máximo es 15 días, han pasado 29 |
| **Resultado** | |
| **Observaciones** | |

---

### QA-017 · Alimentación · Fuera de plazo (plazo muy corto: 14 días)
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0017` |
| **Categoría** | alimentacion |
| **Producto** | Aceite |
| **Motivo** | wrong_item |
| **Plazo máx.** | 14 días 🚨 plazo muy corto |
| **Días desde entrega** | 16 |
| **Importe** | 15.99 € |
| **Saludo chat** | `Problema con el pedido` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0017. Recibí aceite de oliva, pedí girasol` |
| **Keywords esperadas** | rechazado, alimentación plazo 14 días, 16 días |
| **Criterios** | Alimentación: 16 días > 14 máximo |
| **Resultado** | |
| **Observaciones** | |

---

### QA-023 · Cosmética · Cambio de opinión (Art. 103 higiene)
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0023` |
| **Categoría** | cosmetica_perfumeria |
| **Producto** | Esmalte |
| **Motivo** | changed_mind |
| **Plazo máx.** | 21 días |
| **Días desde entrega** | 8 |
| **Importe** | 14.99 € |
| **Saludo chat** | `Problema con el pedido` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0023. El esmalte no me gusta, color diferente` |
| **Keywords esperadas** | rechazado, higiene sensible, Art. 103 |
| **Criterios** | Cosmética + cambio opinión + abierto = rechazo legal |
| **Resultado** | |
| **Observaciones** | |

---

## Casos HITL 🔄 — Derivar a revisión humana

### QA-002 · Bebé · Importe > 100€
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0002` |
| **Categoría** | bebe_puericultura |
| **Producto** | Cochecito |
| **Motivo** | defective |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 7 |
| **Importe** | 299.99 € 🔴 > 100€ |
| **Saludo chat** | `Necesito ayuda con una devolución` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0002. El cochecito tiene defecto en la rueda frontal` |
| **Keywords esperadas** | derivado a HITL, importe > 100€ |
| **Criterios** | Plazo OK · Defecto válido · Pero 299.99€ > 100€ = HITL automático |
| **Resultado** | |
| **Observaciones** | |

---

### QA-005 · Deportes · Importe > 100€
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0005` |
| **Categoría** | deportes_aire_libre |
| **Producto** | Bicicleta |
| **Motivo** | defective |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 17 |
| **Importe** | 399.99 € 🔴 > 100€ |
| **Saludo chat** | `Necesito ayuda urgente` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0005. La bicicleta tiene defecto en el cambio` |
| **Keywords esperadas** | derivado a HITL, importe > 100€ |
| **Criterios** | Plazo OK · Defecto válido · Pero 399.99€ >> 100€ = HITL |
| **Resultado** | |
| **Observaciones** | |

---

### QA-009 · Electrodomésticos · Importe > 100€
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0009` |
| **Categoría** | electrodomesticos |
| **Producto** | Nevera |
| **Motivo** | defective |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 9 |
| **Importe** | 849.99 € 🔴 > 100€ |
| **Saludo chat** | `Acabo de recibir` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0009. La nevera hace ruido extraño, tiene defecto` |
| **Keywords esperadas** | derivado a HITL, importe 849.99€ |
| **Criterios** | Plazo OK · Defecto válido · Pero 849.99€ >> 100€ = HITL |
| **Resultado** | |
| **Observaciones** | |

---

### QA-010 · Electrónica · Importe > 100€
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0010` |
| **Categoría** | electronica_informatica |
| **Producto** | Portátil |
| **Motivo** | missing_parts |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 15 |
| **Importe** | 899.99 € 🔴 > 100€ |
| **Saludo chat** | `Acabo de abrir el portátil` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0010. Falta el cargador en la caja` |
| **Keywords esperadas** | derivado a HITL, importe 899.99€ |
| **Criterios** | Plazo OK · Piezas faltantes · Pero 899.99€ >> 100€ = HITL |
| **Resultado** | |
| **Observaciones** | |

---

### QA-014 · Muebles · Importe > 100€ + Cliente frecuente ⚠️
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0014` |
| **Categoría** | muebles |
| **Producto** | Sofá |
| **Motivo** | defective |
| **Plazo máx.** | 14 días |
| **Días desde entrega** | 2 |
| **Importe** | 1299.99 € 🔴 > 100€ |
| **Saludo chat** | `Acabo de recibir el sofá` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0014. El sofá tiene una costura rota` |
| **Keywords esperadas** | derivado a HITL, importe 1299.99€, cliente frecuente |
| **Criterios** | Cliente frecuente (cust-14) + importe muy alto = HITL doble |
| **Resultado** | |
| **Observaciones** | |

---

### QA-018 · Electrodomésticos · Importe > 100€
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0018` |
| **Categoría** | electrodomesticos |
| **Producto** | Lavadora |
| **Motivo** | defective |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 24 |
| **Importe** | 549.99 € 🔴 > 100€ |
| **Saludo chat** | `Acabo de comprar una lavadora` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0018. La lavadora no centrifuga bien` |
| **Keywords esperadas** | derivado a HITL, importe 549.99€ |
| **Criterios** | Plazo OK · Defecto válido · Pero 549.99€ > 100€ = HITL |
| **Resultado** | |
| **Observaciones** | |

---

### QA-019 · Calzado · Importe > 100€ (aunque talla válida)
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0019` |
| **Categoría** | calzado |
| **Producto** | Botas |
| **Motivo** | wrong_size |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 25 |
| **Importe** | 119.99 € 🔴 > 100€ |
| **Saludo chat** | `Cambiar las botas` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0019. Las botas son 41, pedí 42` |
| **Keywords esperadas** | derivado a HITL, importe 119.99€ |
| **Criterios** | Talla válida pero 119.99€ > 100€ = HITL de todas formas |
| **Resultado** | |
| **Observaciones** | |

---

### QA-020 · Bebé · Importe > 100€ + Equipo de seguridad
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0020` |
| **Categoría** | bebe_puericultura |
| **Producto** | Silla coche |
| **Motivo** | defective |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 6 |
| **Importe** | 199.99 € 🔴 > 100€ |
| **Saludo chat** | `Problema urgente` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0020. La silla de coche tiene defecto en el arnés` |
| **Keywords esperadas** | derivado a HITL, importe 199.99€, seguridad bebé |
| **Criterios** | Equipo de seguridad + importe alto = HITL |
| **Resultado** | |
| **Observaciones** | |

---

### QA-024 · Electrónica · Importe > 100€
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0024` |
| **Categoría** | electronica_informatica |
| **Producto** | Teclado |
| **Motivo** | defective |
| **Plazo máx.** | 30 días |
| **Días desde entrega** | 23 |
| **Importe** | 129.99 € 🔴 > 100€ |
| **Saludo chat** | `El teclado está defectuoso` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0024. El teclado tiene teclas que no funcionan` |
| **Keywords esperadas** | derivado a HITL, importe 129.99€ |
| **Criterios** | Defecto válido pero 129.99€ > 100€ = HITL |
| **Resultado** | |
| **Observaciones** | |

---

## Caso AMBIGUO ⚠️

### QA-021 · Droguería · Defectuoso (higiene sensible)
| Campo | Valor |
|-------|-------|
| **Pedido** | `ORD-QA-0021` |
| **Categoría** | drogueria_salud |
| **Producto** | Loción |
| **Motivo** | defective |
| **Plazo máx.** | 21 días |
| **Días desde entrega** | 11 |
| **Importe** | 19.99 € |
| **Saludo chat** | `La loción tiene un problema` |
| **Mensaje pedido** | `Es el pedido ORD-QA-0021. La loción parece contaminada` |
| **Keywords esperadas** | aprobada O rechazada según si está abierta |
| **Criterios** | Higiene sensible: si sin abrir → aprobada · si abierta → rechazada por Art. 103 |
| **Resultado** | |
| **Observaciones** | |

---

## Resumen de resultados

| ID | Tipo | Categoría | Resultado esperado | ✓/✗ |
|----|------|-----------|-------------------|-----|
| QA-001 | ✅ | Alimentación | Aprobada automáticamente | |
| QA-002 | 🔄 | Bebé | HITL — importe > 100€ | |
| QA-003 | ✅ | Calzado | Aprobada automáticamente | |
| QA-004 | ❌ | Cosmética | Rechazada — Art. 103 higiene | |
| QA-005 | 🔄 | Deportes | HITL — importe > 100€ | |
| QA-006 | ❌ | Droguería | Rechazada — Art. 103 higiene | |
| QA-007 | ❌ | Libros | Rechazada — fuera de plazo | |
| QA-008 | ✅ | Mascotas | Aprobada automáticamente | |
| QA-009 | 🔄 | Electrodomésticos | HITL — importe > 100€ | |
| QA-010 | 🔄 | Electrónica | HITL — importe > 100€ | |
| QA-011 | ✅ | Jardinería | Aprobada automáticamente | |
| QA-012 | ✅ | Juguetes | Aprobada automáticamente | |
| QA-013 | ✅ | Moda | Aprobada automáticamente | |
| QA-014 | 🔄 | Muebles | HITL — importe > 100€ + cliente frecuente | |
| QA-015 | ✅ | Hogar | Aprobada automáticamente | |
| QA-016 | ❌ | Joyería | Rechazada — fuera de plazo (29 vs 15) | |
| QA-017 | ❌ | Alimentación | Rechazada — fuera de plazo (16 vs 14) | |
| QA-018 | 🔄 | Electrodomésticos | HITL — importe > 100€ | |
| QA-019 | 🔄 | Calzado | HITL — importe > 100€ | |
| QA-020 | 🔄 | Bebé | HITL — importe > 100€ + seguridad | |
| QA-021 | ⚠️ | Droguería | Ambiguo — depende si está abierta | |
| QA-022 | ✅ | Alimentación | Aprobada automáticamente | |
| QA-023 | ❌ | Cosmética | Rechazada — Art. 103 higiene | |
| QA-024 | 🔄 | Electrónica | HITL — importe > 100€ | |

**Total: ✅ 8 válidos · ❌ 6 inválidos · 🔄 9 HITL · ⚠️ 1 ambiguo**
