# Defender la arquitectura MCP con Docker y FastMCP

## 1. Arquitectura: un contenedor Docker por cada servidor MCP

### El planteamiento
Cada dominio funcional del sistema vive en su propio contenedor Docker independiente. Por ejemplo, un MCP para la base de datos SQL, otro para consultar una API externa, y otro para gestionar el sistema de ficheros local.

### Argumentos para defenderlo
- **Aislamiento de fallos:** Si un servidor MCP que conecta con una API externa se cae, el resto de los contenedores MCP siguen operando normalmente. El agente de IA mantiene acceso a los demás servicios y herramientas.
- **Seguridad y principio de menor privilegio:** Cada contenedor tiene su propio espacio de nombres, variables de entorno y credenciales limitadas. El MCP de ficheros solo accede al volumen necesario; si es vulnerable, el impacto se confina a ese contenedor.
- **Independencia de dependencias:** Un MCP puede necesitar librerías Python pesadas y otro solo llamadas HTTP ligeras. Docker evita conflictos de dependencias y mantiene cada entorno limpio.
- **Despliegues y actualizaciones atómicas:** Puedes actualizar, parchear o reiniciar un único MCP sin tocar ni recompilar el resto de la arquitectura.

## 2. El núcleo del desarrollo: ¿por qué usar FastMCP?

### El planteamiento
Implementar MCP desde cero obliga a manejar JSON-RPC, sesiones, esquemas y validación de tipos. Con FastMCP, aprovechas una capa de alto rendimiento inspirada en FastAPI que abstrae esa complejidad.

### Argumentos para defenderlo
- **Desarrollo pythonico y menos boilerplate:** Con `@mcp.tool`, expones una función de Python como herramienta sin escribir lógica de protocolo manualmente.
- **Generación automática de esquemas:** FastMCP usa las anotaciones de tipos y docstrings para generar JSON Schema. Define `user_id: int` y FastMCP valida la entrada antes de ejecutar tu función.
- **Estándar de la industria:** FastMCP es una opción madura y recomendada en Python para servidores MCP por su robustez y simplicidad.

## 3. Preguntas frecuentes y objeciones comunes

### Objeción: "¿No es excesivo levantar un contenedor Docker por cada MCP? Añade complejidad de red."
No es sobrecarga, es modularidad. Docker Compose gestiona la red interna y los contenedores se comunican localmente de forma segura. Además, esta separación facilita la escalabilidad horizontal cuando un MCP sufre alta carga.

### Objeción: "¿Por qué no meter todo en un solo script de Python grande?"
Eso genera deuda técnica y mantenimiento difícil. Un monolito acopla todos los accesos a datos y servicios. Con micro-MCPs en Docker, cada componente se mantiene, prueba y despliega por separado.

### Objeción: "¿FastMCP añade latencia o restricciones?"
Al contrario, acelera el time-to-market. FastMCP abstrae la complejidad del protocolo MCP de bajo nivel y reduce bugs de integración entre el LLM y el backend.

## 4. Ejemplo rápido de componente con FastMCP

```python
from fastmcp import FastMCP

mcp = FastMCP("Database-Connector-MCP")

@mcp.tool()
def consultar_stock_producto(producto_id: int) -> str:
    """Consulta el stock actual de un producto en la base de datos local."""
    return f"El producto {producto_id} tiene 45 unidades disponibles."

if __name__ == "__main__":
    mcp.run()
```

## 5. Resumen para la presentación

> "Optamos por una arquitectura desacoplada basada en contenedores Docker independientes por cada servidor MCP para garantizar aislamiento de fallos, seguridad por compartimentación y despliegues independientes. Para hacerlo eficiente a nivel de desarrollo y evitar código repetitivo de bajo nivel, implementamos FastMCP, lo que nos permite transformar código Python tipado en herramientas listas para agentes de IA de forma limpia, estandarizada y robusta."
