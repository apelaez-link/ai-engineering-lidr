# 02 — Plantillas de prompts y prompting desde backend

> Material del curso LIDR · AI Engineering · Sesión 4 (Antonio Pérez). (≈22 min)

## El problema del f-string
Empiezas con un prompt como f-string en el endpoint. Funciona. Dos semanas después: añades ejemplos, metes un `if` para `detail_level`, otro para `phases_table`, otro para un cliente concreto... Acabas con un endpoint de 200 líneas donde el prompt está esparcido entre f-strings y condicionales, mezclado con lógica, y nadie sabe qué prompt está activo. No puedes testearlo, ni hacer rollback, ni explicar qué prompt usa un cliente, ni comparar versiones. **El prompt es un artefacto de software, no un mensaje.**

## El prompt como artefacto: tres componentes
- **Estructura fija** — lo que no cambia entre requests (rol, instrucciones, formato, few-shot, reglas). Vive en el repo, versionado.
- **Variables** — datos de cada request (descripción, archivos, contexto RAG). Vienen en el body.
- **Parámetros** — modos que configuran el comportamiento (detail_level, output_format, idioma, tono). Vienen del formulario, tipados.

El **template** une los tres: estructura literal + marcadores de variables + bloques condicionales por parámetros. El motor (Jinja2) compone y produce el texto final.

## Organización en el servicio
```
app/prompts/
├── loader.py
└── estimation/
    └── v1/
        ├── system.j2
        ├── user.j2
        └── examples.j2
```
Tres ideas: (1) los prompts viven separados del código (editables sin tocar Python, PRs legibles); (2) cada caso de uso versionado por número (`v1/`, `v2/`) → no editas, creas un `v2/` al lado (evals comparativos, rollback, versiones por cliente); (3) cada versión separa `system` (rol+instrucciones) / `user` (entrada) / `examples` (few-shot), como recomienda Anthropic y como encaja con la API (roles system/user).

`system.j2` (resumen):
```jinja
You are a senior project estimator ... in {{ project_type | replace('_', ' ') }} projects.
<output_format>
{% if output_format == "phases_table" %}
Return a markdown table: phase, duration_weeks, cost_eur, confidence_pct.
{% elif output_format == "narrative" %}
Return prose in three paragraphs: overview, breakdown, risks.
{% endif %}
</output_format>
<detail_level>{{ detail_level }}</detail_level>
{% if detail_level == "detailed" %}
For every phase, list assumptions and a confidence interval.
{% endif %}
{% include "estimation/v1/examples.j2" %}
```
`user.j2`: minimal → `<project_description>{{ description }}</project_description>`.

## El loader
```python
from jinja2 import Environment, FileSystemLoader, StrictUndefined
_env = Environment(loader=FileSystemLoader(PROMPTS_DIR),
    trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=False, undefined=StrictUndefined)

def render_estimation_prompt(request, version="v1") -> tuple[str, str]:
    system = _env.get_template(f"estimation/{version}/system.j2")
    user = _env.get_template(f"estimation/{version}/user.j2")
    ctx = {"project_type": request.project_type.value, "detail_level": request.detail_level.value,
           "output_format": request.output_format.value, "description": request.description}
    return system.render(**ctx), user.render(**ctx)
```
- **`StrictUndefined`**: cualquier variable no provista rompe con error claro en vez de renderizar vacío en silencio.
- **`trim_blocks`/`lstrip_blocks`**: controlan los saltos de línea de los `{% %}`.
- **`version="v1"`**: cambiar de versión sin tocar el resto del código.

## XML tags vs Markdown
Anthropic recomienda **XML tags** (`<context>`, `<instructions>`) — Claude se entrenó atendiéndolos. OpenAI tiende a **Markdown** (`## Context`). Ambos modelos entienden los dos; es calibración fina. La consistencia importa más que la convención. Los XML tags **no** son HTML: son delimitadores de texto, sin parser ni schema.

## Lo que cambia
El prompt vive en el repo (git, PRs), se testea (test del template, sin coste de API), se versiona y compara, y se lee sin saber Python. El endpoint queda limpio: `system, user = render_estimation_prompt(request)` → llamada al LLM con roles separados.

## Recursos
- Anthropic — *Prompt templates and variables*, *Use XML tags*, *Prompt engineering overview*
- OpenAI — *Prompt engineering* · Jinja2 — *Template Designer Documentation*
