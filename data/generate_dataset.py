"""
Generador determinista de dataset sintético para ReFlow.

Produce, a partir de listas de clientes/productos ficticios y de las políticas
de devolución redactadas en dataset/policies/*.md:

  - supabase/seed_synthetic.sql   -> INSERTs para customers, products, orders,
                                      order_items, return_policies,
                                      return_requests, return_items.
  - dataset/eval_cases.csv        -> "golden dataset" etiquetado (valid /
                                      invalid / human_review) para evaluar el
                                      Agente Evaluador de Políticas (Épica 2 /
                                      Épica 5 de doc/guia.md).

Uso:
    python dataset/generate_dataset.py

No requiere dependencias externas (solo librería estándar) ni acceso a
Supabase/OpenAI: es un generador offline, reproducible (random.seed fijo).
"""

from __future__ import annotations

import csv
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

SEED = 20260730
rng = random.Random(SEED)

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICIES_DIR = Path(__file__).resolve().parent / "rag" / "policies"
OUT_SQL = REPO_ROOT / "supabase" / "seed_synthetic.sql"
# El golden dataset de evaluación no tiene ningún consumidor en producción —
# solo lo leen evaluation/golden/scripts/ — así que vive junto a esos scripts,
# no en data/ (que sí alimenta producción/dev vía OUT_SQL y rag/policies/).
OUT_EVAL_CSV = REPO_ROOT / "evaluation" / "golden" / "eval_cases.csv"
OUT_STATS = REPO_ROOT / "evaluation" / "golden" / "GENERATION_STATS.md"

TODAY = datetime(2026, 7, 30, 12, 0, 0)

# ---------------------------------------------------------------------------
# 1. Catálogo de categorías y configuración de política (debe coincidir con
#    los documentos en dataset/policies/*.md)
# ---------------------------------------------------------------------------

HYGIENE_SENSITIVE = {
    "cosmetica_perfumeria",
    "drogueria_salud",
    "bebe_puericultura",
    "alimentacion",
    "mascotas",
}

CATEGORIES = {
    "electronica_informatica": dict(
        label="Electrónica e Informática",
        prefix="ELEC",
        max_return_days=30,
        requires_original_packaging=True,
        restocking_fee_percent=15.00,
        allowed_conditions=[
            "unopened",
            "opened_tested",
            "defective",
            "wrong_item",
            "damaged_in_transit",
        ],
        policy_doc="01_electronica_informatica.md",
    ),
    "electrodomesticos": dict(
        label="Electrodomésticos",
        prefix="ELDO",
        max_return_days=30,
        requires_original_packaging=True,
        restocking_fee_percent=10.00,
        allowed_conditions=[
            "unopened",
            "defective",
            "wrong_item",
            "damaged_in_transit",
            "missing_parts",
        ],
        policy_doc="02_electrodomesticos.md",
    ),
    "moda_ropa": dict(
        label="Moda y Complementos",
        prefix="MODA",
        max_return_days=30,
        requires_original_packaging=False,
        restocking_fee_percent=0.00,
        allowed_conditions=[
            "unopened",
            "wrong_size",
            "wrong_item",
            "not_as_described",
            "defective",
        ],
        policy_doc="03_moda_ropa.md",
    ),
    "calzado": dict(
        label="Calzado",
        prefix="CALZ",
        max_return_days=30,
        requires_original_packaging=True,
        restocking_fee_percent=0.00,
        allowed_conditions=["unopened", "wrong_size", "defective", "wrong_item"],
        policy_doc="04_calzado.md",
    ),
    "joyeria_relojes": dict(
        label="Joyería y Relojería",
        prefix="JOYA",
        max_return_days=15,
        requires_original_packaging=True,
        restocking_fee_percent=0.00,
        allowed_conditions=["unopened", "defective", "wrong_item", "not_as_described"],
        policy_doc="05_joyeria_relojeria.md",
    ),
    "hogar_decoracion": dict(
        label="Hogar y Decoración",
        prefix="HOGA",
        max_return_days=30,
        requires_original_packaging=False,
        restocking_fee_percent=0.00,
        allowed_conditions=[
            "unopened",
            "opened_unused",
            "defective",
            "wrong_item",
            "damaged_in_transit",
        ],
        policy_doc="06_hogar_decoracion.md",
    ),
    "muebles": dict(
        label="Muebles",
        prefix="MUEB",
        max_return_days=14,
        requires_original_packaging=True,
        restocking_fee_percent=10.00,
        allowed_conditions=[
            "unopened",
            "defective",
            "damaged_in_transit",
            "wrong_item",
        ],
        policy_doc="07_muebles.md",
    ),
    "jardineria_bricolaje": dict(
        label="Jardinería y Bricolaje",
        prefix="JARD",
        max_return_days=30,
        requires_original_packaging=True,
        restocking_fee_percent=5.00,
        allowed_conditions=[
            "unopened",
            "defective",
            "wrong_item",
            "damaged_in_transit",
        ],
        policy_doc="08_jardineria_bricolaje.md",
    ),
    "juguetes": dict(
        label="Juguetes",
        prefix="JUGU",
        max_return_days=30,
        requires_original_packaging=True,
        restocking_fee_percent=0.00,
        allowed_conditions=["unopened", "defective", "wrong_item", "not_as_described"],
        policy_doc="09_juguetes.md",
    ),
    "bebe_puericultura": dict(
        label="Bebé y Puericultura",
        prefix="BEBE",
        max_return_days=30,
        requires_original_packaging=True,
        restocking_fee_percent=0.00,
        allowed_conditions=["unopened", "defective", "wrong_item"],
        policy_doc="10_bebe_puericultura.md",
    ),
    "deportes_aire_libre": dict(
        label="Deportes y Aire Libre",
        prefix="DEPO",
        max_return_days=30,
        requires_original_packaging=True,
        restocking_fee_percent=5.00,
        allowed_conditions=["unopened", "opened_tested", "defective", "wrong_item"],
        policy_doc="11_deportes_aire_libre.md",
    ),
    "cosmetica_perfumeria": dict(
        label="Cosmética y Perfumería",
        prefix="COSM",
        max_return_days=21,
        requires_original_packaging=True,
        restocking_fee_percent=0.00,
        allowed_conditions=["unopened", "defective", "wrong_item"],
        policy_doc="12_cosmetica_perfumeria.md",
    ),
    "drogueria_salud": dict(
        label="Droguería, Higiene y Salud",
        prefix="DROG",
        max_return_days=21,
        requires_original_packaging=True,
        restocking_fee_percent=0.00,
        allowed_conditions=["unopened", "defective", "wrong_item"],
        policy_doc="13_drogueria_salud.md",
    ),
    "alimentacion": dict(
        label="Alimentación y Gran Consumo",
        prefix="ALIM",
        max_return_days=14,
        requires_original_packaging=True,
        restocking_fee_percent=0.00,
        allowed_conditions=["unopened", "defective", "wrong_item"],
        policy_doc="14_alimentacion.md",
    ),
    "mascotas": dict(
        label="Mascotas",
        prefix="MASC",
        max_return_days=21,
        requires_original_packaging=True,
        restocking_fee_percent=0.00,
        allowed_conditions=["unopened", "defective", "wrong_item"],
        policy_doc="15_mascotas.md",
    ),
    "libros_papeleria": dict(
        label="Libros, Papelería y Oficina",
        prefix="LIBR",
        max_return_days=21,
        requires_original_packaging=False,
        restocking_fee_percent=0.00,
        allowed_conditions=["unopened", "wrong_item", "defective"],
        policy_doc="16_libros_papeleria.md",
    ),
}

PRODUCT_CATALOG = {
    "electronica_informatica": [
        (
            'Nortek UltraBook 14" Ryzen 7 16GB/512GB',
            "Portátil ligero con procesador Ryzen 7, 16GB RAM y SSD 512GB",
            749.99,
            1.4,
        ),
        (
            'Nortek UltraBook 14" i5 8GB/256GB',
            "Portátil de uso diario con Intel i5, 8GB RAM y SSD 256GB",
            549.99,
            1.4,
        ),
        (
            "Vionix Smartphone Aurora 128GB",
            'Smartphone con pantalla AMOLED 6.5" y 128GB de almacenamiento',
            399.99,
            0.18,
        ),
        (
            "Vionix Smartphone Aurora Pro 256GB 5G",
            "Smartphone 5G con triple cámara y 256GB de almacenamiento",
            599.99,
            0.19,
        ),
        (
            'Quantia Tablet Air 10.5" 64GB',
            "Tablet ligera con pantalla de 10.5 pulgadas y 64GB",
            249.99,
            0.45,
        ),
        (
            "Pulsar Auriculares TWS Cancelación de Ruido",
            "Auriculares inalámbricos con cancelación activa de ruido",
            89.99,
            0.05,
        ),
        (
            "Pulsar Altavoz Bluetooth Portátil 360°",
            "Altavoz resistente al agua con sonido envolvente 360°",
            59.99,
            0.6,
        ),
        (
            'Nortek Monitor Curvo 27" 144Hz',
            "Monitor gaming curvo con panel a 144Hz",
            259.99,
            4.2,
        ),
        (
            "Vionix Smartwatch Fit 2",
            "Reloj inteligente con monitor de ritmo cardíaco y GPS",
            129.99,
            0.06,
        ),
        (
            "Quantia Cámara Instantánea Retro",
            "Cámara de fotos instantáneas de diseño retro",
            79.99,
            0.35,
        ),
        (
            "Nortek Disco SSD Externo 1TB USB-C",
            "Disco SSD externo portátil de 1TB con conexión USB-C",
            79.99,
            0.05,
        ),
        (
            "Pulsar Teclado Mecánico RGB",
            "Teclado mecánico retroiluminado RGB para gaming",
            69.99,
            0.9,
        ),
        (
            "Vionix Ratón Inalámbrico Ergonómico",
            "Ratón inalámbrico ergonómico de alta precisión",
            29.99,
            0.12,
        ),
        (
            "Quantia Dron Compacto con Cámara 4K",
            "Dron plegable con cámara 4K estabilizada",
            349.99,
            0.6,
        ),
    ],
    "electrodomesticos": [
        (
            "Frescor Frigorífico Combi No Frost 300L",
            "Frigorífico combi de bajo consumo con tecnología No Frost",
            549.99,
            65,
        ),
        (
            "Frescor Congelador Vertical 200L",
            "Congelador vertical de gran capacidad, clase energética A+",
            399.99,
            45,
        ),
        (
            "HomeLine Lavadora Carga Frontal 8kg",
            "Lavadora de carga frontal con 12 programas",
            379.99,
            60,
        ),
        (
            "HomeLine Lavavajillas Integrable 12 servicios",
            "Lavavajillas integrable con capacidad para 12 servicios",
            429.99,
            45,
        ),
        (
            "Cucina Horno Multifunción Empotrable",
            "Horno empotrable con 8 funciones de cocinado",
            289.99,
            30,
        ),
        (
            "Cucina Microondas con Grill 25L",
            "Microondas de 25 litros con función grill",
            99.99,
            12,
        ),
        (
            "HomeLine Aspiradora Robot Navegación Láser",
            "Robot aspirador con navegación láser y mapeo de estancias",
            219.99,
            3.5,
        ),
        (
            "Cucina Cafetera Superautomática",
            "Cafetera superautomática con molinillo integrado",
            349.99,
            8,
        ),
        (
            "HomeLine Batidora de Vaso 1200W",
            "Batidora de vaso profesional con 6 velocidades",
            69.99,
            2.5,
        ),
        (
            "Cucina Freidora de Aire 5.5L",
            "Freidora sin aceite de 5.5 litros de capacidad",
            89.99,
            4,
        ),
        (
            "Frescor Vinoteca 18 Botellas",
            "Vinoteca compacta con capacidad para 18 botellas",
            199.99,
            20,
        ),
        (
            "HomeLine Plancha de Vapor Vertical",
            "Plancha de vapor vertical para prendas delicadas",
            79.99,
            3,
        ),
    ],
    "moda_ropa": [
        (
            "Urbano Camiseta Algodón Orgánico",
            "Camiseta básica de algodón 100% orgánico",
            14.99,
            0.15,
        ),
        (
            "Urbano Pantalón Chino Slim Fit",
            "Pantalón chino de corte slim fit",
            34.99,
            0.4,
        ),
        (
            "Nordic Wear Abrigo Parka Impermeable",
            "Abrigo parka impermeable con capucha desmontable",
            129.99,
            1.1,
        ),
        (
            "Nordic Wear Chaqueta de Cuero Premium",
            "Chaqueta de cuero auténtico de corte clásico",
            199.99,
            1.2,
        ),
        (
            "Bellamoda Vestido Midi Estampado",
            "Vestido midi con estampado floral de temporada",
            44.99,
            0.3,
        ),
        ("Bellamoda Blusa Satinada", "Blusa satinada de manga larga", 29.99, 0.2),
        (
            "Urbano Sudadera con Capucha",
            "Sudadera de algodón con capucha y bolsillo canguro",
            39.99,
            0.5,
        ),
        ("Urbano Vaqueros Rectos", "Vaqueros de corte recto y tiro medio", 44.99, 0.6),
        (
            "Nordic Wear Jersey de Lana Merino",
            "Jersey de lana merino de cuello redondo",
            59.99,
            0.4,
        ),
        ("Bellamoda Falda Plisada", "Falda plisada midi de tejido fluido", 27.99, 0.25),
        ("Urbano Bañador Deportivo", "Bañador deportivo de secado rápido", 19.99, 0.1),
        (
            "Urbano Ropa Interior Pack 3",
            "Pack de 3 unidades de ropa interior de algodón",
            14.99,
            0.1,
        ),
        (
            "Nordic Wear Guantes Térmicos",
            "Guantes térmicos táctiles para invierno",
            17.99,
            0.1,
        ),
        (
            "Bellamoda Bufanda de Punto",
            "Bufanda de punto grueso tejida a mano",
            15.99,
            0.15,
        ),
    ],
    "calzado": [
        (
            "StridePro Zapatillas Running ProAir",
            "Zapatillas de running con amortiguación de aire",
            89.99,
            0.7,
        ),
        (
            "StridePro Zapatillas Trail Grip",
            "Zapatillas de trail running con suela de alto agarre",
            99.99,
            0.8,
        ),
        (
            "Caminar Botas de Montaña Impermeables",
            "Botas de montaña con membrana impermeable",
            119.99,
            1.1,
        ),
        (
            "Caminar Zapato de Vestir Piel",
            "Zapato de vestir de piel genuina",
            79.99,
            0.9,
        ),
        (
            "StridePro Zapatillas Casual Urbanas",
            "Zapatillas casuales de estilo urbano",
            59.99,
            0.6,
        ),
        ("Caminar Sandalias de Verano", "Sandalias planas de verano", 29.99, 0.4),
        (
            "StridePro Zapatillas Infantiles Luces LED",
            "Zapatillas infantiles con luces LED en la suela",
            34.99,
            0.5,
        ),
        ("Caminar Botines de Piel Mujer", "Botines de piel de tacón bajo", 69.99, 0.8),
        (
            "StridePro Zapatillas de Baloncesto",
            "Zapatillas de baloncesto de caña alta",
            94.99,
            0.85,
        ),
        (
            "Caminar Mocasines de Ante",
            "Mocasines de ante con forro interior",
            64.99,
            0.6,
        ),
        (
            "StridePro Chanclas de Piscina Pack 2",
            "Pack de 2 pares de chanclas de piscina",
            12.99,
            0.2,
        ),
        ("Caminar Botas de Agua", "Botas de agua antideslizantes", 24.99, 0.7),
    ],
    "joyeria_relojes": [
        (
            "Aurelia Collar Plata de Ley con Circonita",
            "Collar de plata de ley con circonita central",
            49.99,
            0.03,
        ),
        (
            "Aurelia Pendientes de Oro 18k",
            "Pendientes de oro de 18 quilates",
            129.99,
            0.02,
        ),
        (
            "Aurelia Anillo Solitario Plata",
            "Anillo solitario de plata de ley",
            39.99,
            0.02,
        ),
        (
            "Cronos Reloj Clásico Automático",
            "Reloj automático de esfera clásica y correa de piel",
            249.99,
            0.15,
        ),
        (
            "Cronos Reloj Deportivo Multifunción",
            "Reloj deportivo con cronógrafo y sumergible 100m",
            149.99,
            0.12,
        ),
        (
            "Aurelia Pulsera de Perlas Cultivadas",
            "Pulsera de perlas cultivadas de agua dulce",
            69.99,
            0.03,
        ),
        (
            "Cronos Smartwatch Elegance",
            "Smartwatch de diseño elegante con correa de acero",
            199.99,
            0.06,
        ),
        (
            "Aurelia Gemelos de Plata Grabados",
            "Gemelos de plata con grabado personalizado",
            44.99,
            0.02,
        ),
        (
            "Cronos Reloj de Bolsillo Vintage",
            "Reloj de bolsillo de estilo vintage",
            89.99,
            0.1,
        ),
        (
            "Aurelia Broche Vintage Esmaltado",
            "Broche vintage con acabado esmaltado",
            34.99,
            0.02,
        ),
    ],
    "hogar_decoracion": [
        (
            "CasaViva Juego de Sartenes Antiadherentes x3",
            "Set de 3 sartenes con recubrimiento antiadherente",
            59.99,
            2.5,
        ),
        (
            "CasaViva Vajilla Porcelana 18 piezas",
            "Vajilla completa de porcelana para 6 comensales",
            79.99,
            8,
        ),
        (
            "Lumina Lámpara de Pie Diseño Nórdico",
            "Lámpara de pie de diseño nórdico minimalista",
            89.99,
            4,
        ),
        (
            "Lumina Set de Velas Aromáticas x4",
            "Set de 4 velas aromáticas en distintos aromas",
            24.99,
            0.8,
        ),
        (
            "CasaViva Juego de Sábanas Algodón 150cm",
            "Juego de sábanas 100% algodón para cama de 150cm",
            39.99,
            1.2,
        ),
        (
            "CasaViva Alfombra Shaggy 160x230",
            "Alfombra de pelo largo 160x230cm",
            99.99,
            6,
        ),
        (
            "Lumina Espejo de Pared Redondo",
            "Espejo de pared redondo con marco metálico",
            49.99,
            3,
        ),
        (
            "CasaViva Cristalería Set 12 Copas",
            "Set de 12 copas de cristal para vino y agua",
            34.99,
            3.5,
        ),
        (
            "Lumina Cojines Decorativos Pack 2",
            "Pack de 2 cojines decorativos de terciopelo",
            19.99,
            0.6,
        ),
        (
            "CasaViva Cortinas Opacas 140x260",
            "Cortinas opacas térmicas 140x260cm",
            29.99,
            1,
        ),
        (
            "Lumina Organizador de Armario Modular",
            "Sistema modular de organización de armario",
            44.99,
            2,
        ),
        (
            "CasaViva Set de Cuchillos de Cocina",
            "Set de cuchillos de cocina con soporte de madera",
            54.99,
            1.5,
        ),
        (
            "Lumina Difusor de Aromas USB",
            "Difusor de aromas por ultrasonidos con conexión USB",
            22.99,
            0.4,
        ),
        (
            "CasaViva Toallas de Baño Pack 4",
            "Pack de 4 toallas de baño de algodón egipcio",
            27.99,
            1.4,
        ),
    ],
    "muebles": [
        (
            "Robledo Sofá 3 Plazas Tela Gris",
            "Sofá de 3 plazas tapizado en tela gris",
            599.99,
            55,
        ),
        (
            "Robledo Mesa de Comedor Extensible",
            "Mesa de comedor extensible de madera maciza",
            349.99,
            40,
        ),
        (
            "Nordika Silla de Oficina Ergonómica",
            "Silla de oficina ergonómica con soporte lumbar",
            179.99,
            15,
        ),
        (
            "Nordika Estantería Modular 5 Baldas",
            "Estantería modular de 5 baldas ajustables",
            129.99,
            20,
        ),
        (
            "Robledo Cama Canapé Abatible 150",
            "Cama canapé abatible con gran capacidad de almacenaje",
            399.99,
            60,
        ),
        (
            "Robledo Colchón Viscoelástico 150x190",
            "Colchón viscoelástico de firmeza media",
            349.99,
            25,
        ),
        (
            "Nordika Armario Ropero 3 Puertas",
            "Armario ropero de 3 puertas con espejo",
            449.99,
            70,
        ),
        ("Nordika Mesa Auxiliar Nido x2", "Juego de 2 mesas auxiliares nido", 79.99, 8),
        (
            "Robledo Cabecero Tapizado 150",
            "Cabecero tapizado en tela para cama de 150",
            149.99,
            12,
        ),
        (
            "Nordika Silla Comedor Pack 2",
            "Pack de 2 sillas de comedor de madera",
            159.99,
            14,
        ),
        (
            "Robledo Sofá Cama Chaise Longue",
            "Sofá cama con chaise longue reversible",
            699.99,
            65,
        ),
        (
            "Nordika Mueble TV Diseño Industrial",
            "Mueble de TV de estilo industrial con ruedas",
            189.99,
            25,
        ),
    ],
    "jardineria_bricolaje": [
        (
            "GreenTool Taladro Percutor Inalámbrico 20V",
            "Taladro percutor inalámbrico con batería de 20V",
            89.99,
            1.8,
        ),
        (
            "GreenTool Cortacésped Eléctrico 1400W",
            "Cortacésped eléctrico con recogedor de hierba",
            149.99,
            12,
        ),
        (
            "TerraVerde Maceta de Cerámica Grande",
            "Maceta de cerámica esmaltada de gran tamaño",
            24.99,
            3,
        ),
        (
            "TerraVerde Kit de Riego por Goteo",
            "Kit completo de riego por goteo para jardín",
            34.99,
            1.5,
        ),
        (
            "GreenTool Motosierra Eléctrica 2000W",
            "Motosierra eléctrica de 2000W de potencia",
            119.99,
            4.5,
        ),
        (
            "TerraVerde Mesa y Sillas de Terraza Set",
            "Set de mesa y 4 sillas para terraza",
            199.99,
            25,
        ),
        (
            "GreenTool Barbacoa de Carbón Portátil",
            "Barbacoa de carbón portátil para exteriores",
            79.99,
            8,
        ),
        (
            "TerraVerde Sustrato Universal 50L",
            "Saco de sustrato universal para plantas de 50L",
            12.99,
            20,
        ),
        (
            "GreenTool Sierra Circular de Mesa",
            "Sierra circular de mesa para bricolaje",
            179.99,
            15,
        ),
        (
            "TerraVerde Fertilizante Líquido Universal 1L",
            "Fertilizante líquido concentrado de uso universal",
            9.99,
            1.1,
        ),
        (
            "GreenTool Set de Herramientas de Mano 45 piezas",
            "Maletín con 45 herramientas de mano",
            49.99,
            3.5,
        ),
        (
            "TerraVerde Sombrilla de Jardín 3m",
            "Sombrilla de jardín de 3 metros de diámetro",
            69.99,
            6,
        ),
        (
            "GreenTool Generador Portátil 2000W",
            "Generador eléctrico portátil de 2000W",
            349.99,
            20,
        ),
        (
            "TerraVerde Planta de Interior Ficus 60cm",
            "Planta de interior Ficus de 60cm de altura",
            29.99,
            4,
        ),
    ],
    "juguetes": [
        (
            "Kidonia Set de Construcción 500 piezas",
            "Set de construcción de bloques de 500 piezas",
            44.99,
            1.2,
        ),
        (
            "PlayNova Muñeca Interactiva Habla",
            "Muñeca interactiva con frases y sonidos",
            34.99,
            0.6,
        ),
        (
            "Kidonia Puzle 1000 piezas Paisaje",
            "Puzle de 1000 piezas con paisaje natural",
            14.99,
            0.7,
        ),
        (
            "PlayNova Pista de Coches Eléctrica",
            "Pista de coches eléctrica con looping",
            59.99,
            2,
        ),
        (
            "Kidonia Peluche Oso Gigante 80cm",
            "Peluche de oso de 80cm de altura",
            29.99,
            0.9,
        ),
        (
            "PlayNova Consola de Juguete Retro",
            "Consola de juguete con juegos retro precargados",
            39.99,
            0.4,
        ),
        (
            "Kidonia Juego de Mesa Familiar",
            "Juego de mesa para toda la familia",
            24.99,
            0.8,
        ),
        (
            "PlayNova Figura de Colección Edición Limitada",
            "Figura de colección de edición limitada numerada",
            49.99,
            0.2,
        ),
        (
            "Kidonia Cocina de Juguete de Madera",
            "Cocina de juguete de madera con accesorios",
            89.99,
            8,
        ),
        (
            "PlayNova Dron de Juguete con Cámara",
            "Dron de juguete con cámara integrada",
            54.99,
            0.4,
        ),
        (
            "Kidonia Set de Ciencia Experimentos",
            "Set de experimentos científicos para niños",
            27.99,
            1,
        ),
        (
            "PlayNova Patinete de Juguete Luces",
            "Patinete infantil con ruedas luminosas",
            32.99,
            2.5,
        ),
    ],
    "bebe_puericultura": [
        (
            "Bebicare Cochecito 3 en 1 Todo Terreno",
            "Cochecito 3 en 1 con capazo y silla de coche",
            349.99,
            14,
        ),
        (
            "Bebicare Silla de Coche Grupo 0+/1",
            "Silla de coche homologada grupo 0+/1",
            199.99,
            8,
        ),
        (
            "Pequenin Cuna Convertible de Madera",
            "Cuna convertible en cama junior",
            249.99,
            30,
        ),
        (
            "Pequenin Trona Regulable en Altura",
            "Trona regulable en altura y reclinación",
            89.99,
            7,
        ),
        (
            "Bebicare Biberón Anticólico Pack 3",
            "Pack de 3 biberones anticólico",
            19.99,
            0.3,
        ),
        (
            "Pequenin Chupete Silicona Pack 2",
            "Pack de 2 chupetes de silicona",
            7.99,
            0.05,
        ),
        (
            "Bebicare Sacaleches Eléctrico Doble",
            "Sacaleches eléctrico de extracción doble",
            129.99,
            1,
        ),
        (
            "Pequenin Body de Algodón Pack 5",
            "Pack de 5 bodies de algodón para bebé",
            24.99,
            0.4,
        ),
        (
            "Bebicare Vigilabebés con Cámara HD",
            "Vigilabebés con cámara HD y visión nocturna",
            99.99,
            0.5,
        ),
        (
            "Pequenin Bañera de Bebé Plegable",
            "Bañera plegable para bebé con soporte",
            39.99,
            2,
        ),
        (
            "Bebicare Portabebés Ergonómico",
            "Portabebés ergonómico multiposición",
            59.99,
            0.6,
        ),
        (
            "Pequenin Parque de Juegos Plegable",
            "Parque de juegos plegable con colchoneta",
            79.99,
            12,
        ),
    ],
    "deportes_aire_libre": [
        (
            'TrailMax Bicicleta de Montaña 27.5"',
            "Bicicleta de montaña con ruedas de 27.5 pulgadas",
            449.99,
            15,
        ),
        (
            "TrailMax Bicicleta Urbana Plegable",
            "Bicicleta urbana plegable para ciudad",
            349.99,
            13,
        ),
        (
            "FitPro Cinta de Correr Plegable",
            "Cinta de correr plegable con pantalla LED",
            399.99,
            40,
        ),
        (
            "FitPro Banco de Musculación Ajustable",
            "Banco de musculación ajustable multiposición",
            179.99,
            22,
        ),
        (
            "TrailMax Tienda de Campaña 4 Personas",
            "Tienda de campaña familiar para 4 personas",
            129.99,
            5,
        ),
        (
            "TrailMax Saco de Dormir -10°C",
            "Saco de dormir para temperaturas de hasta -10°C",
            59.99,
            1.5,
        ),
        (
            "FitPro Esterilla de Yoga Antideslizante",
            "Esterilla de yoga antideslizante de 6mm",
            24.99,
            1,
        ),
        (
            "FitPro Guantes de Boxeo Pro",
            "Guantes de boxeo profesionales acolchados",
            34.99,
            0.5,
        ),
        (
            "TrailMax Mochila de Trekking 40L",
            "Mochila de trekking de 40 litros de capacidad",
            69.99,
            1.2,
        ),
        (
            "FitPro Patinete Eléctrico Urbano",
            "Patinete eléctrico urbano plegable",
            349.99,
            13,
        ),
        (
            "TrailMax Caña de Pescar Telescópica",
            "Caña de pescar telescópica de fibra de carbono",
            44.99,
            0.6,
        ),
        (
            "FitPro Set de Mancuernas Ajustables",
            "Set de mancuernas ajustables de peso variable",
            149.99,
            20,
        ),
    ],
    "cosmetica_perfumeria": [
        (
            "Essenza Eau de Parfum Floral 90ml",
            "Eau de parfum de notas florales, 90ml",
            59.99,
            0.3,
        ),
        (
            "Essenza Eau de Toilette Cítrico 100ml",
            "Eau de toilette de notas cítricas, 100ml",
            44.99,
            0.3,
        ),
        (
            "PureSkin Crema Facial Antiedad",
            "Crema facial antiedad con ácido hialurónico",
            34.99,
            0.15,
        ),
        (
            "PureSkin Sérum Vitamina C",
            "Sérum facial con vitamina C concentrada",
            29.99,
            0.1,
        ),
        (
            "Essenza Set de Maquillaje Profesional",
            "Set de maquillaje profesional con paleta de sombras",
            49.99,
            0.5,
        ),
        (
            "PureSkin Mascarilla Facial de Arcilla",
            "Mascarilla facial purificante de arcilla verde",
            14.99,
            0.2,
        ),
        (
            "Essenza Perfume de Viaje Pack 3x20ml",
            "Pack de 3 perfumes de viaje de 20ml",
            39.99,
            0.15,
        ),
        (
            "PureSkin Aceite Corporal Hidratante",
            "Aceite corporal hidratante de argán",
            19.99,
            0.25,
        ),
        (
            "Essenza Labial Mate Larga Duración",
            "Labial mate de larga duración",
            12.99,
            0.03,
        ),
        (
            "PureSkin Champú Reparador Sin Sulfatos",
            "Champú reparador sin sulfatos para cabello dañado",
            9.99,
            0.4,
        ),
        (
            "Essenza Colonia Infantil Suave 100ml",
            "Colonia infantil de fórmula suave, 100ml",
            17.99,
            0.15,
        ),
        (
            "PureSkin Kit de Manicura Profesional",
            "Kit de manicura profesional con estuche",
            24.99,
            0.3,
        ),
    ],
    "drogueria_salud": [
        (
            "VitaPlus Multivitamínico 60 comprimidos",
            "Complejo multivitamínico, 60 comprimidos",
            14.99,
            0.15,
        ),
        (
            "VitaPlus Colágeno con Magnesio 300g",
            "Colágeno hidrolizado con magnesio, bote de 300g",
            22.99,
            0.35,
        ),
        (
            "CleanHome Detergente Líquido 5L",
            "Detergente líquido para lavadora, garrafa de 5L",
            12.99,
            5.2,
        ),
        ("CleanHome Lejía Multiusos 2L", "Lejía multiusos concentrada, 2L", 2.99, 2.1),
        (
            "VitaPlus Cepillo de Dientes Eléctrico",
            "Cepillo de dientes eléctrico recargable",
            39.99,
            0.3,
        ),
        (
            "CleanHome Desinfectante Multisuperficie",
            "Desinfectante multisuperficie apto para cocina y baño",
            4.99,
            1,
        ),
        (
            "VitaPlus Tensiómetro Digital de Brazo",
            "Tensiómetro digital de brazo con memoria",
            34.99,
            0.4,
        ),
        (
            "VitaPlus Termómetro Digital Infrarrojo",
            "Termómetro digital de infrarrojos sin contacto",
            19.99,
            0.1,
        ),
        (
            "CleanHome Suavizante Concentrado 3L",
            "Suavizante concentrado para ropa, 3L",
            8.99,
            3,
        ),
        (
            "VitaPlus Báscula de Bioimpedancia",
            "Báscula de baño con análisis de bioimpedancia",
            29.99,
            1.5,
        ),
        (
            "CleanHome Papel Higiénico Pack 24",
            "Papel higiénico de doble capa, pack de 24 rollos",
            11.99,
            4,
        ),
        (
            "VitaPlus Botiquín de Primeros Auxilios",
            "Botiquín completo de primeros auxilios",
            24.99,
            0.8,
        ),
    ],
    "alimentacion": [
        (
            "Huerto Real Aceite de Oliva Virgen Extra 1L",
            "Aceite de oliva virgen extra de primera prensada, 1L",
            8.99,
            1,
        ),
        (
            "Huerto Real Pack Conservas Variadas x12",
            "Pack de 12 conservas variadas de verduras y pescado",
            19.99,
            3.5,
        ),
        (
            "Despensa Ibérica Jamón Curado Loncheado 200g",
            "Jamón curado loncheado envasado al vacío, 200g",
            6.99,
            0.2,
        ),
        (
            "Despensa Ibérica Pasta Italiana Pack 6",
            "Pack de 6 formatos de pasta italiana",
            7.99,
            3,
        ),
        (
            "Huerto Real Arroz Bomba 1kg",
            "Arroz bomba de denominación de origen, 1kg",
            3.49,
            1,
        ),
        (
            "Despensa Ibérica Café en Grano 1kg",
            "Café en grano de tueste natural, 1kg",
            12.99,
            1,
        ),
        (
            "Huerto Real Miel Artesana 500g",
            "Miel artesana de flores silvestres, 500g",
            6.49,
            0.6,
        ),
        (
            "Despensa Ibérica Vino Tinto Reserva",
            "Vino tinto reserva D.O., botella 750ml",
            9.99,
            1.2,
        ),
        (
            "Huerto Real Frutos Secos Selección 1kg",
            "Selección de frutos secos variados, 1kg",
            11.99,
            1,
        ),
        (
            "Despensa Ibérica Chocolate Negro 70% Pack 5",
            "Pack de 5 tabletas de chocolate negro 70%",
            9.99,
            0.5,
        ),
        (
            "Huerto Real Cerveza Artesana Pack 12",
            "Pack de 12 botellines de cerveza artesana",
            14.99,
            4.8,
        ),
        (
            "Despensa Ibérica Snacks Salados Pack Familiar",
            "Pack familiar de snacks salados variados",
            8.99,
            1.2,
        ),
    ],
    "mascotas": [
        (
            "PetLoop Pienso para Perro Adulto 15kg",
            "Pienso completo para perro adulto, saco de 15kg",
            44.99,
            15,
        ),
        (
            "PetLoop Pienso para Gato Esterilizado 10kg",
            "Pienso para gato esterilizado, saco de 10kg",
            34.99,
            10,
        ),
        (
            "AnimalFeliz Transportín de Viaje Homologado",
            "Transportín rígido homologado para viajes",
            49.99,
            3,
        ),
        (
            "AnimalFeliz Cama Acolchada para Perro",
            "Cama acolchada lavable para perro",
            29.99,
            1.5,
        ),
        (
            "PetLoop Arena Aglomerante para Gatos 10L",
            "Arena aglomerante con control de olores, 10L",
            9.99,
            8,
        ),
        (
            "AnimalFeliz Correa Retráctil 5m",
            "Correa retráctil de 5 metros con freno",
            14.99,
            0.4,
        ),
        (
            "PetLoop Snacks Dentales para Perro Pack",
            "Pack de snacks dentales para perro",
            7.99,
            0.5,
        ),
        (
            "AnimalFeliz Rascador para Gatos Torre",
            "Rascador tipo torre con varios niveles",
            39.99,
            6,
        ),
        (
            "PetLoop Comedero Automático con Temporizador",
            "Comedero automático programable con temporizador",
            34.99,
            1.2,
        ),
        (
            "AnimalFeliz Juguete Interactivo para Perro",
            "Juguete interactivo dispensador de premios",
            12.99,
            0.3,
        ),
    ],
    "libros_papeleria": [
        (
            "Letra Viva Novela Best Seller Tapa Dura",
            "Novela superventas en edición de tapa dura",
            21.99,
            0.5,
        ),
        (
            "Letra Viva Colección Clásicos Pack 5",
            "Pack de 5 novelas clásicas de la literatura universal",
            39.99,
            1.8,
        ),
        (
            "OficinaPro Agenda Anual 2026/2027",
            "Agenda anual con vista semanal, curso 2026/2027",
            12.99,
            0.4,
        ),
        (
            "OficinaPro Set de Bolígrafos Premium x10",
            "Set de 10 bolígrafos premium de gel",
            9.99,
            0.2,
        ),
        (
            "Letra Viva Libro de Cocina Ilustrado",
            "Libro de recetas ilustrado a todo color",
            24.99,
            0.9,
        ),
        (
            "OficinaPro Cuadernos A5 Pack 3",
            "Pack de 3 cuadernos tapa dura A5",
            8.99,
            0.5,
        ),
        (
            "Letra Viva Cómic Edición Coleccionista",
            "Cómic en edición coleccionista numerada",
            17.99,
            0.4,
        ),
        (
            "OficinaPro Tóner Compatible Multicolor",
            "Tóner compatible multicolor para impresora láser",
            29.99,
            0.6,
        ),
        (
            "Letra Viva Libro Infantil Ilustrado",
            "Cuento infantil ilustrado a todo color",
            13.99,
            0.3,
        ),
        (
            "OficinaPro Mochila Escolar Reforzada",
            "Mochila escolar reforzada con múltiples compartimentos",
            34.99,
            0.9,
        ),
        (
            "Letra Viva Diccionario Bilingüe",
            "Diccionario bilingüe español-inglés",
            19.99,
            1.1,
        ),
        (
            "OficinaPro Calculadora Científica",
            "Calculadora científica de 240 funciones",
            16.99,
            0.2,
        ),
    ],
}

# ---------------------------------------------------------------------------
# 2. Clientes ficticios
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "María",
    "Carlos",
    "Laura",
    "Javier",
    "Ana",
    "David",
    "Elena",
    "Pablo",
    "Marta",
    "Sergio",
    "Lucía",
    "Diego",
    "Sara",
    "Alejandro",
    "Cristina",
    "Miguel",
    "Paula",
    "Adrián",
    "Isabel",
    "Raúl",
    "Nuria",
    "Óscar",
    "Rocío",
    "Iván",
    "Beatriz",
    "Rubén",
    "Silvia",
    "Fernando",
    "Patricia",
    "Álvaro",
    "Carmen",
    "Jorge",
    "Irene",
    "Manuel",
    "Andrea",
    "Antonio",
    "Natalia",
    "Francisco",
    "Eva",
    "Víctor",
    "Alba",
    "Rodrigo",
    "Sandra",
    "Hugo",
    "Claudia",
    "Mario",
    "Julia",
    "Gonzalo",
    "Marina",
    "Ignacio",
]

LAST_NAMES = [
    "García",
    "Martínez",
    "López",
    "Fernández",
    "Ruiz",
    "Soto",
    "Gómez",
    "Díaz",
    "Álvarez",
    "Romero",
    "Navarro",
    "Torres",
    "Domínguez",
    "Vázquez",
    "Ramos",
    "Gil",
    "Serrano",
    "Blanco",
    "Suárez",
    "Molina",
    "Ortega",
    "Delgado",
    "Castro",
    "Ortiz",
    "Rubio",
    "Marín",
    "Sanz",
    "Iglesias",
    "Nuñez",
    "Medina",
    "Cortés",
    "Santos",
    "Guerrero",
    "Cano",
    "Prieto",
    "Vega",
    "Herrera",
    "Peña",
    "Flores",
    "Cabrera",
]

CITIES = [
    ("Madrid", "28013"),
    ("Barcelona", "08018"),
    ("Sevilla", "41004"),
    ("Valencia", "46002"),
    ("Bilbao", "48005"),
    ("Zaragoza", "50001"),
    ("Málaga", "29005"),
    ("Murcia", "30001"),
    ("Palma", "07001"),
    ("Las Palmas de Gran Canaria", "35001"),
    ("Alicante", "03001"),
    ("Córdoba", "14001"),
    ("Valladolid", "47001"),
    ("Vigo", "36201"),
    ("Gijón", "33201"),
    ("A Coruña", "15001"),
    ("Granada", "18001"),
    ("San Sebastián", "20001"),
    ("Santander", "39001"),
    ("Toledo", "45001"),
]

STREET_TYPES = ["Calle", "Avenida", "Plaza", "Paseo"]
STREET_NAMES = [
    "Mayor",
    "Gran Vía",
    "de la Constitución",
    "del Sol",
    "de la Paz",
    "San Francisco",
    "Alcalá",
    "Diagonal",
    "Sierpes",
    "de la Rosa",
    "Colón",
    "del Prado",
    "Real",
    "Nueva",
    "de Andalucía",
    "Reyes Católicos",
]

EMAIL_DOMAINS = ["gmail.com", "hotmail.com", "outlook.com", "yahoo.es", "mail.com"]


@dataclass
class Customer:
    """Cliente ficticio del dataset sintético."""

    id: str
    email: str
    full_name: str
    phone: str
    city: str
    postal_code: str
    street: str


def build_customers(n: int) -> list[Customer]:
    """Genera `n` clientes ficticios con nombre completo y email únicos."""
    used_names: set[str] = set()
    used_emails: set[str] = set()
    customers = []
    while len(customers) < n:
        first = rng.choice(FIRST_NAMES)
        last1 = rng.choice(LAST_NAMES)
        last2 = rng.choice(LAST_NAMES)
        full_name = f"{first} {last1} {last2}"
        if full_name in used_names:
            continue
        used_names.add(full_name)
        base_email = (
            f"{first.lower()}.{last1.lower()}".replace("á", "a")
            .replace("é", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ú", "u")
            .replace("ñ", "n")
        )
        domain = rng.choice(EMAIL_DOMAINS)
        email = f"{base_email}@{domain}"
        suffix = 1
        while email in used_emails:
            suffix += 1
            email = f"{base_email}{suffix}@{domain}"
        used_emails.add(email)
        city, postal_prefix = rng.choice(CITIES)
        street = f"{rng.choice(STREET_TYPES)} {rng.choice(STREET_NAMES)} {rng.randint(1, 200)}"
        postal_code = f"{postal_prefix[:2]}{rng.randint(0, 99):03d}"
        phone = f"+346{rng.randint(0, 9)}{rng.randint(1000000, 9999999)}"
        customers.append(
            Customer(
                id=str(uuid.uuid4()),
                email=email,
                full_name=full_name,
                phone=phone,
                city=city,
                postal_code=postal_code,
                street=street,
            )
        )
    return customers


# ---------------------------------------------------------------------------
# 3. Productos
# ---------------------------------------------------------------------------


@dataclass
class Product:
    """Producto ficticio del catálogo sintético."""

    id: str
    sku: str
    name: str
    description: str
    category: str
    price: float
    weight_kg: float


def build_products() -> list[Product]:
    """Construye la lista completa de productos a partir de `PRODUCT_CATALOG`."""
    products = []
    for category, items in PRODUCT_CATALOG.items():
        prefix = CATEGORIES[category]["prefix"]
        for idx, (name, desc, price, weight) in enumerate(items, start=1):
            products.append(
                Product(
                    id=str(uuid.uuid4()),
                    sku=f"{prefix}-{idx:03d}",
                    name=name,
                    description=desc,
                    category=category,
                    price=price,
                    weight_kg=weight,
                )
            )
    return products


# ---------------------------------------------------------------------------
# 4. Pedidos y líneas de pedido
# ---------------------------------------------------------------------------


@dataclass
class OrderItem:
    """Línea de un pedido: producto, cantidad y precios."""

    id: str
    order_id: str
    product: Product
    quantity: int
    unit_price: float
    total_price: float


@dataclass
class Order:
    """Pedido ficticio con sus líneas de artículo asociadas."""

    id: str
    customer: Customer
    order_number: str
    status: str
    total_amount: float
    ordered_at: datetime
    delivered_at: datetime | None
    items: list[OrderItem] = field(default_factory=list)


ORDER_STATUS_WEIGHTS = [
    ("delivered", 78),
    ("shipped", 6),
    ("processing", 5),
    ("cancelled", 6),
    ("returned", 5),
]


def weighted_choice(pairs, rng_local):
    """Elige un valor al azar respetando los pesos indicados.

    Args:
        pairs: Lista de tuplas `(valor, peso)` entre las que elegir.
        rng_local: Instancia de `random.Random` a usar (permite generadores
            independientes del `rng` global del módulo).

    Returns:
        El valor elegido según los pesos relativos.
    """
    total = sum(w for _, w in pairs)
    r = rng_local.uniform(0, total)
    upto = 0
    for value, weight in pairs:
        upto += weight
        if upto >= r:
            return value
    return pairs[-1][0]


def shipping_days_for_category(category: str, rng_local) -> int:
    """Simula los días de envío según si la categoría es de artículos pesados.

    Returns:
        Días de envío simulados (rango mayor para categorías pesadas).
    """
    heavy = {
        "electrodomesticos",
        "muebles",
        "jardineria_bricolaje",
        "deportes_aire_libre",
    }
    if category in heavy:
        return rng_local.randint(4, 10)
    return rng_local.randint(1, 5)


_order_counters: dict[int, int] = {}


def next_order_number(ordered_at: datetime) -> str:
    """Genera el siguiente número de pedido correlativo para el año de `ordered_at`."""
    year = ordered_at.year
    _order_counters[year] = _order_counters.get(year, 0) + 1
    return f"ORD-{year}-{_order_counters[year]:05d}"


def build_orders(
    customers: list[Customer],
    products: list[Product],
    n_orders: int,
    frequent_customer_ids: set[str],
) -> list[Order]:
    """Genera pedidos sintéticos repartidos entre clientes y categorías.

    Args:
        customers: Clientes disponibles para asignar como comprador.
        products: Catálogo de productos entre los que elegir líneas de pedido.
        n_orders: Número total de pedidos a generar.
        frequent_customer_ids: IDs de clientes marcados como devolvedores
            frecuentes, sobrerrepresentados en los pedidos generados.

    Returns:
        Lista de pedidos con sus líneas, estado y fechas de envío simulados.
    """
    by_category: dict[str, list[Product]] = {}
    for p in products:
        by_category.setdefault(p.category, []).append(p)
    categories = list(by_category.keys())

    customers_by_id = {c.id: c for c in customers}
    frequent_customers = [customers_by_id[cid] for cid in frequent_customer_ids]

    orders = []
    for _ in range(n_orders):
        if frequent_customers and rng.random() < 0.35:
            customer = rng.choice(frequent_customers)
        else:
            customer = rng.choice(customers)

        days_ago = rng.randint(3, 420)
        ordered_at = TODAY - timedelta(
            days=days_ago, hours=rng.randint(0, 23), minutes=rng.randint(0, 59)
        )

        multi_category = rng.random() < 0.2
        chosen_categories = (
            rng.sample(categories, 2) if multi_category else [rng.choice(categories)]
        )

        order_id = str(uuid.uuid4())
        order_items = []
        total_amount = 0.0
        for cat in chosen_categories:
            n_items = rng.randint(1, 2) if multi_category else rng.randint(1, 3)
            pool = by_category[cat]
            for _ in range(n_items):
                product = rng.choice(pool)
                qty = rng.choices([1, 1, 1, 2, 2, 3], k=1)[0]
                unit_price = product.price
                total_price = round(unit_price * qty, 2)
                order_items.append(
                    OrderItem(
                        id=str(uuid.uuid4()),
                        order_id=order_id,
                        product=product,
                        quantity=qty,
                        unit_price=unit_price,
                        total_price=total_price,
                    )
                )
                total_amount += total_price
        total_amount = round(total_amount, 2)

        status = weighted_choice(ORDER_STATUS_WEIGHTS, rng)
        max_ship_days = max(
            shipping_days_for_category(oi.product.category, rng) for oi in order_items
        )
        delivered_at = None
        if status in ("delivered", "returned"):
            delivered_at = ordered_at + timedelta(
                days=max_ship_days, hours=rng.randint(0, 12)
            )
            if delivered_at > TODAY:
                delivered_at = TODAY - timedelta(days=1)
                status = "shipped"
        elif status == "shipped":
            delivered_at = None

        orders.append(
            Order(
                id=order_id,
                customer=customer,
                order_number=next_order_number(ordered_at),
                status=status,
                total_amount=total_amount,
                ordered_at=ordered_at,
                delivered_at=delivered_at,
                items=order_items,
            )
        )
    return orders


# ---------------------------------------------------------------------------
# 5. Casos de devolución (return_requests / return_items) con etiqueta de
#    evaluación (valid / invalid / human_review) derivada de la política
#    general (dataset/policies/00_marco_general_devoluciones.md, sección 5).
# ---------------------------------------------------------------------------

STORE_FAULT_REASONS = [
    "defective",
    "wrong_item_shipped",
    "damaged_in_transit",
    "missing_parts",
    "not_as_described",
]
CUSTOMER_FAULT_REASONS = [
    "changed_mind",
    "wrong_size",
    "better_price_found",
    "quality_issue",
]
SPECIAL_REASONS = [
    "allergic_reaction",
    "duplicate_order",
    "arrived_late",
    "assembly_issue",
    "incompatible",
    "counterfeit_suspicion",
]

CONDITION_FOR_REASON = {
    "defective": ["defective"],
    "wrong_item_shipped": ["wrong_item"],
    "damaged_in_transit": ["damaged_in_transit"],
    "missing_parts": ["missing_parts"],
    "not_as_described": ["not_as_described", "opened_unused"],
    "changed_mind": ["unopened", "opened_unused", "opened_tested"],
    "wrong_size": ["wrong_size", "unopened"],
    "better_price_found": ["unopened"],
    "quality_issue": ["opened_tested", "opened_unused"],
    "allergic_reaction": ["opened_unused", "defective"],
    "duplicate_order": ["unopened"],
    "arrived_late": ["unopened"],
    "assembly_issue": ["defective", "unopened"],
    "incompatible": ["wrong_item", "unopened"],
    "counterfeit_suspicion": ["not_as_described"],
}

# Varias redacciones por motivo (distinto tono/registro: formal, coloquial,
# escueto, con detalle) para que el texto libre de `return_requests.reason`
# no sea una única frase repetida en todo el dataset. "{product}" se sustituye
# por el nombre del primer artículo devuelto cuando la frase lo incluye.
REASON_TEXT_VARIANTS = {
    "defective": [
        "El producto presenta un defecto de fabricación.",
        "{product} no funciona desde que lo saqué de la caja.",
        "Se ha estropeado nada más usarlo, parece un fallo de fábrica.",
        "No enciende / no funciona correctamente, creo que viene defectuoso.",
        "Al abrir el paquete comprobé que {product} tiene un fallo de fabricación.",
        "Está roto de fábrica, no debería haber pasado el control de calidad.",
        "Tiene un problema técnico desde el primer uso, no es normal.",
        "buenas, el articulo q me llego no va bien, esta fallado de fabrica",
    ],
    "wrong_item_shipped": [
        "Se recibió un artículo distinto al pedido.",
        "Pedí otra cosa y me ha llegado {product}, no es lo mismo.",
        "El paquete no corresponde con lo que compré.",
        "Han enviado un producto equivocado, no es el que aparece en mi pedido.",
        "Esto no es lo que yo compré, se han confundido en el almacén.",
        "me an mandado otra cosa distinta a lo q pedi",
    ],
    "damaged_in_transit": [
        "El producto llegó dañado por el transporte.",
        "La caja venía golpeada y {product} ha llegado roto.",
        "Ha llegado con daños visibles, seguramente por el envío.",
        "El paquete estaba aplastado y el contenido dañado.",
        "Llegó con un golpe importante, no se puede usar así.",
        "el paquete venia todo abollado y el producto roto por dentro",
    ],
    "missing_parts": [
        "Faltan piezas o accesorios en el paquete recibido.",
        "A {product} le falta una pieza según el manual de instrucciones.",
        "El paquete venía incompleto, faltan accesorios.",
        "No venían todos los tornillos/piezas para montarlo.",
        "Falta el cargador que debería incluir la caja.",
    ],
    "not_as_described": [
        "El producto no coincide con la descripción publicada.",
        "{product} no se parece a las fotos de la ficha del producto.",
        "Las medidas o el color no coinciden con lo anunciado en la web.",
        "No es como lo describían en la página, me siento engañado/a.",
        "La calidad y el material no corresponden a lo que ponía el anuncio.",
    ],
    "changed_mind": [
        "El cliente ha cambiado de opinión sobre la compra.",
        "Al final no me convence, prefiero devolverlo.",
        "Lo compré por impulso y ya no lo quiero.",
        "Ya no lo necesito, ha sido un error de compra.",
        "Buenas, quería devolver esto porque ya no me hace falta.",
        "Me lo pensé mejor y prefiero el reembolso.",
        "no era lo q esperaba, prefiero devolverlo",
    ],
    "wrong_size": [
        "La talla o medida no es la correcta.",
        "{product} me queda pequeño/a, necesitaría una talla más.",
        "Le queda grande, ¿se puede cambiar de talla?",
        "No es la talla que pedí, ha habido un error al elegir.",
        "Me está pequeño, quisiera cambiarlo por una talla más grande.",
    ],
    "better_price_found": [
        "El cliente encontró un precio mejor en otro lugar.",
        "Lo he visto más barato en otra tienda justo después de comprarlo.",
        "He encontrado una oferta mejor, preferiría anular esta compra.",
        "Vi el mismo producto más barato en otro sitio, quiero devolverlo.",
    ],
    "quality_issue": [
        "El cliente percibe una calidad inferior a la esperada.",
        "{product} se siente de peor calidad de lo que esperaba por el precio.",
        "No me convence el acabado, esperaba más calidad.",
        "El material no es tan bueno como parecía en las fotos.",
        "La calidad general me ha decepcionado un poco.",
    ],
    "allergic_reaction": [
        "El cliente reporta una reacción alérgica al usar el producto.",
        "Me ha salido una reacción en la piel después de usar {product}.",
        "Tuve una reacción alérgica, se me irritó la piel.",
        "Me sentó mal / me dio una reacción rara nada más probarlo.",
        "Me ha salido un sarpullido después de usarlo, no sé si soy alérgico/a a algún componente.",
    ],
    "duplicate_order": [
        "El pedido se realizó por error de forma duplicada.",
        "Se me duplicó el pedido sin querer, solo necesito uno.",
        "Por error he hecho dos pedidos iguales, quiero anular uno.",
        "Me han llegado dos unidades cuando solo compré una, creo que se duplicó el pago.",
    ],
    "arrived_late": [
        "El pedido llegó fuera de plazo y ya no se necesita.",
        "Ha llegado tan tarde que ya no me hace falta, era para una fecha concreta.",
        "El envío se retrasó mucho y ya no tiene sentido quedármelo.",
        "Lo necesitaba para un evento que ya ha pasado, llegó demasiado tarde.",
    ],
    "assembly_issue": [
        "El cliente reporta problemas de montaje o instalación.",
        "No consigo montar {product}, las instrucciones no coinciden con las piezas.",
        "Al montarlo se rompió una pieza, creo que el diseño falla.",
        "Es imposible instalarlo siguiendo el manual, algo no encaja.",
    ],
    "incompatible": [
        "El producto es incompatible con el uso previsto por el cliente.",
        "{product} no es compatible con mi equipo, aunque la ficha decía que sí.",
        "No funciona con lo que tengo en casa, esperaba que fuera compatible.",
        "No encaja / no es compatible con el sistema que ya tengo.",
    ],
    "counterfeit_suspicion": [
        "El cliente sospecha que el producto no es original.",
        "{product} no parece el original, el acabado es distinto al de otras veces.",
        "Tengo dudas de que sea un producto original, algo no cuadra.",
        "Creo que esto podría ser una réplica, no coincide con lo que esperaba de la marca.",
    ],
}


def render_reason_text(case: "ReturnCase") -> str:
    """Genera el texto libre del motivo de un caso a partir de `REASON_TEXT_VARIANTS`.

    Returns:
        Una redacción aleatoria del motivo, con el nombre del producto
        sustituido cuando la plantilla lo incluye.
    """
    variants = REASON_TEXT_VARIANTS[case.reason_category]
    template = rng.choice(variants)
    if "{product}" in template:
        product_name = case.return_items[0][0].product.name
        return template.format(product=product_name)
    return template


DAY_BUCKETS = [
    ("deep_inside_window", 62),
    ("near_boundary", 10),
    ("just_over_boundary", 8),
    ("far_past_deadline", 20),
]


@dataclass
class ReturnCase:
    """Caso de devolución sintético, con su etiqueta de evaluación (valid/invalid/human_review)."""

    id: str
    order: Order
    customer: Customer
    return_items: list[tuple[OrderItem, int, str]]  # (order_item, qty, condition)
    reason_category: str
    status: str
    resolution: str | None
    refund_amount: float
    notes: str
    created_at: datetime
    resolved_at: datetime | None
    tracking_number: str | None
    label: str  # valid | invalid | human_review
    rationale: str
    days_since_delivery: int


def sample_days(cfg_max_days: int) -> tuple[int, str]:
    """Muestrea días transcurridos desde la entrega según un bucket ponderado del plazo.

    Returns:
        Tupla `(días, bucket)`, donde `bucket` indica la franja simulada
        respecto al plazo (dentro de plazo, cerca del límite, justo
        excedido o muy tardía).
    """
    bucket = weighted_choice(DAY_BUCKETS, rng)
    if bucket == "deep_inside_window":
        days = rng.randint(1, max(1, cfg_max_days - 6))
    elif bucket == "near_boundary":
        days = rng.randint(max(1, cfg_max_days - 2), cfg_max_days + 2)
    elif bucket == "just_over_boundary":
        days = rng.randint(cfg_max_days + 3, cfg_max_days + 5)
    else:
        days = rng.randint(cfg_max_days + 10, cfg_max_days + 150)
    return days, bucket


def classify_case(
    cfg_max_days: int,
    days: int,
    condition: str,
    allowed_conditions: list[str],
    reason: str,
    category: str,
    refund_amount: float,
    is_frequent_returner: bool,
    missing_evidence: bool,
) -> tuple[str, str]:
    """Clasifica un caso de devolución como valid/invalid/human_review según la política.

    Args:
        cfg_max_days: Plazo máximo de devolución (días) de la categoría.
        days: Días transcurridos desde la entrega hasta la solicitud.
        condition: Estado declarado del artículo devuelto.
        allowed_conditions: Estados admitidos por la política de la categoría.
        reason: Motivo de la devolución declarado por el cliente.
        category: Categoría del producto devuelto.
        refund_amount: Importe a reembolsar.
        is_frequent_returner: Si el cliente está marcado como devolvedor frecuente.
        missing_evidence: Si falta evidencia fotográfica exigible para el motivo.

    Returns:
        Tupla `(label, rationale)` con la etiqueta de evaluación y la
        justificación textual de la decisión.
    """
    diff = days - cfg_max_days
    reasons: list[str] = []

    hygiene_excluded = (
        category in HYGIENE_SENSITIVE
        and reason in ("changed_mind", "quality_issue", "better_price_found")
        and condition in ("opened_unused", "opened_tested", "used")
    )
    condition_not_allowed = condition not in allowed_conditions and condition not in (
        "damaged",
        "used",
        "missing_parts",
    )

    if hygiene_excluded:
        return "invalid", (
            f"Motivo '{reason}' con precinto de higiene/seguridad roto (condición '{condition}') "
            f"en categoría sujeta a exclusión legal de higiene/perecederos (art. 103 TRLGDCU). "
            f"Rechazo automático con independencia del plazo ({days} días de {cfg_max_days})."
        )

    if diff > 5:
        return "invalid", (
            f"Plazo de devolución superado ampliamente: {days} días desde la entrega frente a un "
            f"máximo de {cfg_max_days} días para esta categoría (más de 5 días de margen excedido). "
            f"Rechazo automático según sección 5 de la política general."
        )

    if condition_not_allowed and reason in CUSTOMER_FAULT_REASONS:
        return "invalid", (
            f"Estado del artículo ('{condition}') no está entre los estados aceptados para esta "
            f"categoría ({', '.join(allowed_conditions)}) y el motivo declarado ('{reason}') no "
            f"corresponde a un fallo imputable a Mercadia."
        )

    if reason in ("allergic_reaction", "counterfeit_suspicion"):
        reasons.append(
            f"motivo sensible ('{reason}') que requiere valoración humana según política general"
        )
    if -2 <= diff <= 5:
        reasons.append(
            f"solicitud en zona frontera del plazo ({days} de {cfg_max_days} días, diferencia {diff:+d})"
        )
    if refund_amount > 100:
        reasons.append(
            f"importe a reembolsar de {refund_amount:.2f} € supera el umbral de 100 € (HITL fijo de la plataforma)"
        )
    if is_frequent_returner:
        reasons.append(
            "cliente con historial de devoluciones por encima del umbral de alerta (posible abuso)"
        )
    if missing_evidence:
        reasons.append("falta evidencia fotográfica exigible para el motivo declarado")

    if reasons:
        return (
            "human_review",
            "Revisión humana obligatoria: " + "; ".join(reasons) + ".",
        )

    return "valid", (
        f"Solicitud dentro de plazo ({days} de {cfg_max_days} días), estado del artículo "
        f"('{condition}') admitido por la política de la categoría e importe dentro del umbral "
        f"de aprobación automática (≤100 €)."
    )


def pick_reason_and_condition(
    category: str, allowed_conditions: list[str]
) -> tuple[str, str]:
    """Elige aleatoriamente un motivo de devolución y una condición de artículo coherentes.

    Args:
        category: Categoría del producto devuelto.
        allowed_conditions: Estados de artículo admitidos por la política de
            la categoría (sesga la elección de condición).

    Returns:
        Tupla `(reason, condition)`.
    """
    roll = rng.random()
    if roll < 0.07:
        reason = rng.choice(SPECIAL_REASONS)
    elif roll < 0.55:
        reason = rng.choice(STORE_FAULT_REASONS)
    else:
        reason = rng.choice(CUSTOMER_FAULT_REASONS)

    candidate_conditions = CONDITION_FOR_REASON.get(reason, ["unopened"])
    # Sesgo: en categorías sensibles a higiene, favorecer condiciones "abiertas"
    # para generar suficientes casos de exclusión legal.
    if (
        category in HYGIENE_SENSITIVE
        and reason in CUSTOMER_FAULT_REASONS
        and rng.random() < 0.5
    ):
        condition = rng.choice(["opened_unused", "opened_tested", "used"])
    else:
        preferred = [c for c in candidate_conditions if c in allowed_conditions]
        condition = (
            rng.choice(preferred) if preferred else rng.choice(candidate_conditions)
        )
    return reason, condition


def build_return_cases(
    orders: list[Order], target_count: int, frequent_customer_ids: set[str]
) -> list[ReturnCase]:
    """Genera casos de devolución sintéticos a partir de los pedidos entregados.

    Args:
        orders: Pedidos entre los que elegir candidatos a devolución (deben
            estar entregados y tener líneas).
        target_count: Número objetivo de casos de devolución a generar.
        frequent_customer_ids: IDs de clientes devolvedores frecuentes,
            priorizados para simular patrones de abuso.

    Returns:
        Lista de casos de devolución con su etiqueta y justificación.
    """
    eligible_orders = [
        o
        for o in orders
        if o.status in ("delivered", "returned") and o.delivered_at and o.items
    ]
    rng.shuffle(eligible_orders)

    cases: list[ReturnCase] = []
    used_orders: set[str] = set()

    # Priorizar a los "clientes frecuentes" para simular patrones de abuso.
    frequent_orders = [
        o for o in eligible_orders if o.customer.id in frequent_customer_ids
    ]
    other_orders = [
        o for o in eligible_orders if o.customer.id not in frequent_customer_ids
    ]

    pool = frequent_orders[:60] + other_orders
    rng.shuffle(pool)

    for order in pool:
        if len(cases) >= target_count:
            break
        if order.id in used_orders:
            continue
        used_orders.add(order.id)

        return_all = (
            rng.random() < 0.15
            and len({oi.product.category for oi in order.items}) == 1
        )
        if return_all:
            chosen_items = order.items
        else:
            chosen_items = [rng.choice(order.items)]

        category = chosen_items[0].product.category
        cfg = CATEGORIES[category]

        days, bucket = sample_days(cfg["max_return_days"])
        reason, condition = pick_reason_and_condition(
            category, cfg["allowed_conditions"]
        )

        return_items_spec = []
        refund_amount = 0.0
        for oi in chosen_items:
            qty_returned = (
                oi.quantity
                if (return_all or rng.random() < 0.8)
                else max(1, oi.quantity - 1)
            )
            line_amount = oi.unit_price * qty_returned
            if (
                reason in CUSTOMER_FAULT_REASONS
                and condition in ("opened_unused", "opened_tested", "used")
                and cfg["restocking_fee_percent"] > 0
            ):
                line_amount *= 1 - cfg["restocking_fee_percent"] / 100
            refund_amount += line_amount
            return_items_spec.append((oi, qty_returned, condition))
        refund_amount = round(refund_amount, 2)

        is_frequent = order.customer.id in frequent_customer_ids
        missing_evidence = reason in STORE_FAULT_REASONS and rng.random() < 0.08

        label, rationale = classify_case(
            cfg["max_return_days"],
            days,
            condition,
            cfg["allowed_conditions"],
            reason,
            category,
            refund_amount,
            is_frequent,
            missing_evidence,
        )

        created_at = order.delivered_at + timedelta(days=days, hours=rng.randint(0, 23))
        if created_at > TODAY:
            created_at = TODAY - timedelta(hours=rng.randint(1, 48))

        if label == "valid":
            status = rng.choices(
                ["approved", "refunded", "closed"], weights=[30, 50, 20]
            )[0]
            resolution = (
                rng.choice(["full_refund", "replacement"])
                if reason in STORE_FAULT_REASONS
                else "full_refund"
            )
            if cfg["restocking_fee_percent"] > 0 and reason in CUSTOMER_FAULT_REASONS:
                resolution = "partial_refund"
            resolved_at = min(created_at + timedelta(days=rng.randint(1, 6)), TODAY)
            tracking_number = f"RET-{uuid.uuid4().hex[:10].upper()}"
            notes = f"[CASE:VALID] Aprobado automáticamente. {rationale}"
        elif label == "invalid":
            status = rng.choice(["rejected", "closed"])
            resolution = "rejected"
            resolved_at = min(created_at + timedelta(days=rng.randint(1, 3)), TODAY)
            tracking_number = None
            notes = f"[CASE:INVALID] Rechazado automáticamente. {rationale}"
        else:
            status = "pending_approval"
            resolution = None
            resolved_at = None
            tracking_number = None
            notes = f"[CASE:HUMAN_REVIEW] Pendiente de aprobación manual (HITL). {rationale}"

        cases.append(
            ReturnCase(
                id=str(uuid.uuid4()),
                order=order,
                customer=order.customer,
                return_items=return_items_spec,
                reason_category=reason,
                status=status,
                resolution=resolution,
                refund_amount=refund_amount,
                notes=notes,
                created_at=created_at,
                resolved_at=resolved_at,
                tracking_number=tracking_number,
                label=label,
                rationale=rationale,
                days_since_delivery=days,
            )
        )

    return cases


# ---------------------------------------------------------------------------
# 6. Utilidades SQL
# ---------------------------------------------------------------------------


def esc(value) -> str:
    """Escapa un valor como literal SQL de texto (o `NULL` si es `None`)."""
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def ts(dt: datetime | None) -> str:
    """Formatea una fecha/hora como literal SQL `timestamptz`, o `NULL` si es `None`."""
    if dt is None:
        return "NULL"
    return esc(dt.strftime("%Y-%m-%d %H:%M:%S+02"))


def sql_array(values: list[str]) -> str:
    """Formatea una lista de strings como literal SQL `ARRAY[...]`."""
    return "ARRAY[" + ", ".join(esc(v) for v in values) + "]"


def load_policy_text(filename: str) -> str:
    """Lee el texto completo del documento de política `filename` desde `POLICIES_DIR`."""
    return (POLICIES_DIR / filename).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 7. Generación principal
# ---------------------------------------------------------------------------


def main() -> None:
    """Genera el dataset sintético completo y escribe los ficheros de salida.

    Construye clientes, productos, pedidos, casos de devolución y
    conversaciones de chat, y escribe el seed SQL (`OUT_SQL`), el golden
    dataset de evaluación (`OUT_EVAL_CSV`) y un resumen de estadísticas de
    generación (`OUT_STATS`).
    """
    n_customers = 320
    n_orders = 1100
    target_returns = 480
    n_frequent_returners = 16

    customers = build_customers(n_customers)
    products = build_products()

    frequent_customer_ids = {c.id for c in rng.sample(customers, n_frequent_returners)}

    orders = build_orders(customers, products, n_orders, frequent_customer_ids)
    return_cases = build_return_cases(orders, target_returns, frequent_customer_ids)

    # --- return_policies: un id por categoría, texto = documento markdown completo ---
    policy_ids = {cat: str(uuid.uuid4()) for cat in CATEGORIES}

    lines: list[str] = []
    lines.append(
        "-- ========================================================================="
    )
    lines.append("-- Dataset sintético de prueba (grande) para ReFlow")
    lines.append("-- Generado por dataset/generate_dataset.py -- NO EDITAR A MANO")
    lines.append(
        f"-- Semilla: {SEED} | Clientes: {len(customers)} | Productos: {len(products)} | "
        f"Pedidos: {len(orders)} | Devoluciones: {len(return_cases)}"
    )
    lines.append("--")
    lines.append(
        "-- Este archivo es el seed único del proyecto. Pensado para cargarse en"
    )
    lines.append("-- una base de datos ya migrada (ver data/README.md).")
    lines.append(
        "-- ========================================================================="
    )
    lines.append("")

    # customers
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append("-- customers")
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append("INSERT INTO customers (id, email, full_name, phone, address) VALUES")
    rows = []
    for c in customers:
        address = (
            f'{{"street": "{c.street}", "city": "{c.city}", '
            f'"postal_code": "{c.postal_code}", "country": "ES"}}'
        )
        rows.append(
            f"    ({esc(c.id)}, {esc(c.email)}, {esc(c.full_name)}, {esc(c.phone)}, {esc(address)}::jsonb)"
        )
    lines.append(",\n".join(rows) + ";")
    lines.append("")

    # products
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append("-- products")
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append(
        "INSERT INTO products (id, sku, name, description, category, price, weight_kg) VALUES"
    )
    rows = []
    for p in products:
        rows.append(
            f"    ({esc(p.id)}, {esc(p.sku)}, {esc(p.name)}, {esc(p.description)}, "
            f"{esc(p.category)}, {p.price:.2f}, {p.weight_kg})"
        )
    lines.append(",\n".join(rows) + ";")
    lines.append("")

    # return_policies
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append(
        "-- return_policies (policy_text = documento markdown completo de dataset/policies/)"
    )
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append(
        "INSERT INTO return_policies (id, category, max_return_days, requires_original_packaging, "
        "restocking_fee_percent, allowed_conditions, policy_text) VALUES"
    )
    rows = []
    for cat, cfg in CATEGORIES.items():
        policy_text = load_policy_text(cfg["policy_doc"])
        rows.append(
            f"    ({esc(policy_ids[cat])}, {esc(cat)}, {cfg['max_return_days']}, "
            f"{'TRUE' if cfg['requires_original_packaging'] else 'FALSE'}, "
            f"{cfg['restocking_fee_percent']:.2f}, {sql_array(cfg['allowed_conditions'])}, "
            f"{esc(policy_text)})"
        )
    lines.append(",\n".join(rows) + ";")
    lines.append("")

    # orders
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append("-- orders")
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append(
        "INSERT INTO orders (id, customer_id, order_number, status, total_amount, "
        "shipping_address, ordered_at, delivered_at) VALUES"
    )
    rows = []
    for o in orders:
        address = (
            f'{{"street": "{o.customer.street}", "city": "{o.customer.city}", '
            f'"postal_code": "{o.customer.postal_code}", "country": "ES"}}'
        )
        rows.append(
            f"    ({esc(o.id)}, {esc(o.customer.id)}, {esc(o.order_number)}, {esc(o.status)}, "
            f"{o.total_amount:.2f}, {esc(address)}::jsonb, {ts(o.ordered_at)}, {ts(o.delivered_at)})"
        )
    lines.append(",\n".join(rows) + ";")
    lines.append("")

    # order_items
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append("-- order_items")
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append(
        "INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES"
    )
    rows = []
    for o in orders:
        for oi in o.items:
            rows.append(
                f"    ({esc(oi.id)}, {esc(o.id)}, {esc(oi.product.id)}, {oi.quantity}, "
                f"{oi.unit_price:.2f}, {oi.total_price:.2f})"
            )
    lines.append(",\n".join(rows) + ";")
    lines.append("")

    # return_requests
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append("-- return_requests")
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append(
        "INSERT INTO return_requests (id, order_id, customer_id, status, reason, reason_category, "
        "resolution, refund_amount, tracking_number, notes, created_at, resolved_at) VALUES"
    )
    rows = []
    for case in return_cases:
        reason_text = render_reason_text(case)
        rows.append(
            f"    ({esc(case.id)}, {esc(case.order.id)}, {esc(case.customer.id)}, {esc(case.status)}, "
            f"{esc(reason_text)}, {esc(case.reason_category)}, {esc(case.resolution)}, "
            f"{case.refund_amount:.2f}, {esc(case.tracking_number)}, {esc(case.notes)}, "
            f"{ts(case.created_at)}, {ts(case.resolved_at)})"
        )
    lines.append(",\n".join(rows) + ";")
    lines.append("")

    # return_items
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append("-- return_items")
    lines.append(
        "-- ---------------------------------------------------------------------------"
    )
    lines.append(
        "INSERT INTO return_items (id, return_request_id, order_item_id, quantity, condition) VALUES"
    )
    rows = []
    for case in return_cases:
        for oi, qty, condition in case.return_items:
            rows.append(
                f"    ({esc(str(uuid.uuid4()))}, {esc(case.id)}, {esc(oi.id)}, {qty}, {esc(condition)})"
            )
    lines.append(",\n".join(rows) + ";")
    lines.append("")

    OUT_SQL.write_text("\n".join(lines), encoding="utf-8")

    # --- eval_cases.csv --------------------------------------------------
    OUT_EVAL_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_EVAL_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        # "condition" y "allowed_conditions" son imprescindibles para poder
        # RE-EVALUAR un caso más tarde (p. ej. desde evaluate_rag.py):
        # classify_case() los usa para calcular expected_label, así que sin
        # exportarlos aquí, cualquier re-evaluación tiene que ADIVINARLOS —
        # con el riesgo de reconstruir un caso distinto al que generó la
        # etiqueta original. allowed_conditions se serializa con "|" como
        # separador (son listas cortas de valores sin "|" en su contenido).
        writer.writerow(
            [
                "case_id",
                "order_number",
                "customer_email",
                "category",
                "reason_category",
                "condition",
                "max_return_days",
                "allowed_conditions",
                "days_since_delivery",
                "refund_amount",
                "expected_label",
                "return_status",
                "is_frequent_returner",
                "rationale",
            ]
        )
        for case in return_cases:
            category = case.return_items[0][0].product.category
            condition = case.return_items[0][2]
            allowed_conditions = "|".join(CATEGORIES[category]["allowed_conditions"])
            writer.writerow(
                [
                    case.id,
                    case.order.order_number,
                    case.customer.email,
                    category,
                    case.reason_category,
                    condition,
                    CATEGORIES[category]["max_return_days"],
                    allowed_conditions,
                    case.days_since_delivery,
                    f"{case.refund_amount:.2f}",
                    case.label,
                    case.status,
                    str(case.customer.id in frequent_customer_ids),
                    case.rationale,
                ]
            )

    # --- estadísticas de generación ---------------------------------------
    label_counts: dict[str, int] = {}
    for case in return_cases:
        label_counts[case.label] = label_counts.get(case.label, 0) + 1

    category_counts: dict[str, int] = {}
    for case in return_cases:
        cat = case.return_items[0][0].product.category
        category_counts[cat] = category_counts.get(cat, 0) + 1

    stats_lines = [
        "# Estadísticas de generación del dataset sintético",
        "",
        f"- Semilla aleatoria: `{SEED}`",
        f"- Clientes: {len(customers)}",
        f"- Productos: {len(products)} (en {len(CATEGORIES)} categorías)",
        f"- Pedidos: {len(orders)}",
        f"- Solicitudes de devolución: {len(return_cases)}",
        f"- Clientes marcados como devolvedores frecuentes: {n_frequent_returners}",
        "",
        "## Distribución de casos por etiqueta esperada (golden dataset)",
        "",
        "| Etiqueta | Nº casos | % |",
        "|---|---|---|",
    ]
    total_cases = len(return_cases) or 1
    for label in ("valid", "invalid", "human_review"):
        count = label_counts.get(label, 0)
        stats_lines.append(f"| {label} | {count} | {100 * count / total_cases:.1f}% |")

    stats_lines += [
        "",
        "## Devoluciones generadas por categoría",
        "",
        "| Categoría | Nº devoluciones |",
        "|---|---|",
    ]
    for cat, count in sorted(category_counts.items(), key=lambda kv: -kv[1]):
        stats_lines.append(f"| {cat} | {count} |")

    OUT_STATS.write_text("\n".join(stats_lines) + "\n", encoding="utf-8")

    print(f"OK -> {OUT_SQL}")
    print(f"OK -> {OUT_EVAL_CSV}")
    print(f"OK -> {OUT_STATS}")
    print(
        f"customers={len(customers)} products={len(products)} orders={len(orders)} "
        f"returns={len(return_cases)}"
    )
    print("label distribution:", label_counts)


if __name__ == "__main__":
    main()
