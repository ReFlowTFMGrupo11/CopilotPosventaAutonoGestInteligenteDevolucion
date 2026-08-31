# Repo methods overview (DRAFT)

Fecha: 2026-08-31
Autor: @copilot (automático)

## ¿Qué es esto?
Este documento es un borrador en la rama `doc/repo-methods-overview` que servirá como "mapa de métodos y responsabilidades" del repositorio ReFlowTFMGrupo11/CopilotPosventaAutonoGestInteligenteDevolucion. Basado en la descripción del proyecto y la composición de lenguajes proporcionada, contiene la estructura esperada, la metodología para extraer la información real de los archivos Python y una plantilla por archivo para completar automáticamente. Este documento marcará claramente las secciones inferidas y las que vienen de análisis AST real.

> Nota importante: al crear este archivo no pude leer el código fuente desde la API. Este documento es un borrador y está diseñado para completarse automáticamente ejecutando el script de extracción AST incluido más abajo (ver sección "Cómo generar la evidencia").

---

### Resumen rápido del proyecto
"ReFlow" es un sistema automatizado de devoluciones y soporte de e-commerce impulsado por agentes de IA generativa en Python. Utiliza LangChain, FastAPI y Streamlit, integrando bases de datos PostgreSQL/pgvector mediante MCP para ofrecer una gestión conversacional de solicitudes.

Stack (provisional)
- Language(s): Python (principal), Shell, PL/pgSQL
- Frameworks / runtime: FastAPI (backend HTTP), Streamlit (UI), LangChain / agentes generativos
- Persistencia: PostgreSQL (+ pgvector), potencial integración Supabase/MCP
- Notable libraries (esperadas): langchain, fastapi, streamlit, psycopg2/asyncpg, pgvector, requests, pydantic

## Propósito de este archivo
1. Actuar como plantilla y punto central para documentar cada archivo `.py` del repo: qué métodos y funciones define, qué hacen (docstring o inferido), y cómo se relacionan entre capas (api, agents, services, models, mcp, frontend, db, tests, otros).
2. Guardar un artefacto inicial (borrador) en la rama `doc/repo-methods-overview` para que el equipo revise y complete una vez se ejecute el análisis de código real.
3. Iniciar un Pull Request (opcional) con este borrador para que los mantenedores decidan el siguiente paso.

## Cómo generar la evidencia (pasos que debes ejecutar en la máquina con el repo clonado)
1. Coloca el siguiente script en `tools/generate_code_map.py` y ejecútalo desde la raíz del repositorio:

```bash
mkdir -p tools
cat > tools/generate_code_map.py <<'PY'
#!/usr/bin/env python3
"""
generate_code_map.py

Recorre el repositorio local, extrae todos los archivos .py (excepto virtualenvs y carpetas comunes a ignorar),
parsea AST para listar:
 - imports (módulos y from imports)
 - clases y métodos con docstrings y firmas
 - funciones top-level con docstrings y firmas
 - llamadas observadas (nombres/atributos) para inferir relaciones

Salida JSON a stdout con detalles por archivo.
"""
import os
import sys
import ast
import json
from pathlib import Path

IGNORED_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules", "build", "dist",
    ".pytest_cache", ".mypy_cache"
}

def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

def get_signature(node: ast.FunctionDef) -> str:
    args = []
    for a in node.args.args:
        if a.arg == "self":
            args.append("self")
        else:
            args.append(a.arg)
    return f"{node.name}({', '.join(args)})"

def analyze_file(path: Path, repo_root: Path) -> dict:
    src = safe_read(path)
    try:
        tree = ast.parse(src)
    except Exception as e:
        return {"path": str(path.relative_to(repo_root)), "error": f"parse error: {e}"}
    imports = []
    classes = []
    functions = []
    calls = set()

    class Visitor(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import):
            for n in node.names:
                imports.append({"type": "import", "name": n.name, "asname": n.asname})
            self.generic_visit(node)
        def visit_ImportFrom(self, node: ast.ImportFrom):
            mod = node.module or ""
            for n in node.names:
                imports.append({"type": "from", "module": mod, "name": n.name, "asname": n.asname})
            self.generic_visit(node)
        def visit_Call(self, node: ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.add(func.id)
            elif isinstance(func, ast.Attribute):
                names = []
                cur = func
                while isinstance(cur, ast.Attribute):
                    names.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    names.append(cur.id)
                call_name = ".".join(reversed(names))
                calls.add(call_name)
            self.generic_visit(node)
        def visit_ClassDef(self, node: ast.ClassDef):
            methods = []
            for n in node.body:
                if isinstance(n, ast.FunctionDef):
                    doc = ast.get_docstring(n) or ""
                    methods.append({
                        "name": n.name,
                        "signature": get_signature(n),
                        "doc": doc.splitlines()[0] if doc else ""
                    })
            doc = ast.get_docstring(node) or ""
            classes.append({"name": node.name, "doc": doc.splitlines()[0] if doc else "", "methods": methods})
            self.generic_visit(node)
        def visit_FunctionDef(self, node: ast.FunctionDef):
            if isinstance(getattr(node, "parent", None), ast.Module):
                doc = ast.get_docstring(node) or ""
                functions.append({"name": node.name, "signature": get_signature(node), "doc": doc.splitlines()[0] if doc else ""})
            self.generic_visit(node)

    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node

    v = Visitor()
    v.visit(tree)

    rel = str(path.relative_to(repo_root))
    return {
        "path": rel,
        "imports": imports,
        "classes": classes,
        "functions": functions,
        "calls": sorted(list(calls)),
    }


def discover_py_files(root: Path):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        for f in filenames:
            if f.endswith('.py'):
                p = Path(dirpath) / f
                out.append(p)
    return out


def layer_from_path(p: str) -> str:
    if p.startswith("backend/models") or p.startswith("backend/models/") :
        return "models"
    if p.startswith("backend/api") or p.startswith("backend/api/"):
        return "api"
    if p.startswith("backend/agents") or p.startswith("backend/agents/"):
        return "agents"
    if p.startswith("backend/services") or p.startswith("backend/services/"):
        return "services"
    if p.startswith("backend/mcp") or p.startswith("backend/mcp/"):
        return "mcp"
    if p.startswith("db") or p.startswith("db/"):
        return "db"
    if p.startswith("supabase") or p.startswith("supabase/"):
        return "supabase"
    if p.startswith("frontend") or p.startswith("frontend/"):
        return "frontend"
    if p.startswith("data") or p.startswith("data/"):
        return "data"
    if p.startswith("tests") or p.startswith("tests/"):
        return "tests"
    return "other"


def main():
    root = Path('.').resolve()
    files = discover_py_files(root)
    files_info = []
    by_layer = {}
    for f in sorted(files):
        rel = str(f.relative_to(root))
        info = analyze_file(f, root)
        info["layer"] = layer_from_path(info["path"])
        files_info.append(info)
        by_layer.setdefault(info["layer"], []).append(info["path"])

    out = {"repo_root": str(root), "files": files_info, "by_layer": by_layer}
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
PY

# Ejecutar:
# python3 tools/generate_code_map.py > docs/code_map.json
```

2. Ejecuta:
   - python3 tools/generate_code_map.py > docs/code_map.json
3. Pegue aquí (en la conversación) o cree un commit con `docs/code_map.json` y avísame. Yo completaré `docs/repo_methods_overview.md` con la información real y lo convertiré en un documento por archivo.

## Plantilla por archivo (.py)
Para cada archivo Python se rellenará la siguiente sección (ejemplo):

- Ruta: backend/agents/graph.py
- Capa: agents
- Resumen (1-2 líneas): ... (usar docstring o inferido)
- Clases:
  - StateGraph
    - Firma constructor: __init__(self, ...)
    - Métodos públicos:
      - add_node(self, node): Añade un nodo. (docstring o inferido)
      - route(self, state): Calcula siguiente nodo. (docstring o inferido)
- Funciones top-level:
  - route_after_triage(state): guard function — decide avanzar a evaluator. (inferido)
- Imports / dependencias: [...]
- Relaciones salientes: importa backend/services/policy.py, backend/models/state.py
- Entrypoint: sí/no
- Notas: inferido — revisar

## Diagrama de alto nivel (texto)
Se generará un diagrama textual que explique el flujo típico: cliente → FastAPI endpoints → capa de services (orquestación) → agents (triage → evaluator → resolution) → modelos persistentes (Postgres/pgvector) y MCP para acciones externas. El archivo final incluirá los módulos concretos que participan en cada etapa, una vez que tenga `docs/code_map.json`.

## Observaciones iniciales (borrador)
- No se pudo acceder al contenido del repo vía API desde el entorno del asistente; la rama existe y este archivo se ha creado en `doc/repo-methods-overview`.
- El documento actual es un borrador que será completado automáticamente usando el script AST.
- Recomendación inmediata: ejecutar el script y subir `docs/code_map.json` o pegarlo en la conversación.

## Acciones siguientes que puedo realizar (elige una o responde)
- A) Ejecutar yo mismo el llenado y crear el documento final en la rama (necesito `docs/code_map.json` o acceso al repo).
- B) Si quieres, procedo a crear un Pull Request desde `doc/repo-methods-overview` hacia `main` con este borrador.
- C) Puedo además generar un `docs/callgraph.dot` a partir del JSON para visualizar dependencias.

Indica qué prefieres: A / B / C (puedes combinar). Si eliges A, sube `docs/code_map.json` o pega su contenido aquí y yo lo usaré para completar el documento.

---

Anexo: ejemplo de sección ya formateada (ejemplo ficticio)

- Ruta: backend/api/main.py
- Capa: api
- Resumen: FastAPI app que monta routers `chat`, `admin` y `orders`. (inferido)
- Clases: —
- Funciones top-level:
  - create_app(): crea y configura la instancia FastAPI (docstring: "Create and configure app")
- Imports: fastapi, backend.routers.chat, backend.services.manager
- Relaciones: llama a backend.services.manager.handle_request → backend.agents.triage
- Entrypoint: sí (uvicorn backend.api.main:app)
- Notas: inferido — revisar docstrings reales
