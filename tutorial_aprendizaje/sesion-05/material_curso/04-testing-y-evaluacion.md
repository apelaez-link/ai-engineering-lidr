# 04 — Testing y evaluación de sistemas con LLMs

> Material del curso LIDR · AI Engineering · Sesión 5 (Antonio Pérez). (≈28 min)

**El choque:** `assert result.total_hours == 16` falla el 30% de las veces aunque el sistema funcione (14/16/18/"10-22h" son todas correctas). El test tradicional no aplica a outputs **probabilísticos**. Dos reacciones malas: abandonar el testing ("no determinista, no se puede testear") o paranoia (revisión manual de 100 casos por cada cambio). Ninguna es sostenible.

**La idea central:** en LLMs el test no comprueba **igualdad** sino **propiedades**. Una respuesta es válida si cumple un conjunto de propiedades verificables.

## Dos errores del `assert == expected`
- **Falsos negativos masivos:** falla porque dijo "16 horas" vs "16h". Acabas con `if "16" in result` → señal perdida.
- **Falsos positivos silenciosos:** pasa porque `len(result) > 0`, mientras producción devuelve "no puedo ayudarte" a todo.

## Tres familias de tests (pirámide)
1. **Hard (deterministas):** la propiedad no depende del modelo (schema válido, campos presentes, rango de horas razonable, nº de componentes ≥1, nombres no vacíos). Baratos, rápidos, sin llamada extra. **La base de la pirámide.**
2. **Soft (deterministas estadísticos):** propiedades de la **distribución** sobre N runs. Ejemplo: **consistencia** — coeficiente de variación de los midpoints < 0.25. Más caros (N llamadas); córrelos en CI, no en cada commit.
3. **Subjetivos (LLM-as-judge):** propiedad genuinamente subjetiva (¿la justificación es coherente con el alcance?). Una 2ª llamada juez (pointwise: score 0-1; pairwise: compara dos). `DeepEval.GEval` lo encapsula. Precauciones: el juez **también se equivoca** (calíbralo), **el umbral importa** (empieza 0.5, ajusta), y **no abuses** (si un regex lo cubre, no uses juez).

## Golden Dataset
Conjunto **curado** de 5-15 casos representativos (simple, medio, grande con dependencias, ambiguo, contradictorio, multilingüe), cada uno **anotado** con criterios de éxito (categoría, rango de horas esperado, componentes/riesgos esperados). Esa metadata es lo que lo hace *golden*. Se consume con `deepeval.dataset.EvaluationDataset` / `Golden`. Construirlo es **inversión** (≈1 h/caso por un experto), se amortiza en la primera regresión evitada. Revísalo cada ~3 meses.

## Suite con DeepEval + pytest
Parametriza cada test por el golden dataset (`@pytest.mark.parametrize("golden", golden_dataset.goldens)`), marca las familias caras con `@pytest.mark.slow` (para `pytest -m "not slow"` en local), y usa **tolerancias generosas en la primera pasada** (detectar fallos catastróficos, no microajustes). DeepEval es nativo pytest, sin infra externa, con métricas listas (AnswerRelevancy, Faithfulness, GEval).

## Anti-patrones
- **Testar la salida del modelo** en vez de las propiedades del sistema (cuando OpenAI actualiza el modelo, todo rompe sin que haya bug).
- Suite que es **solo familia 3** (lentísima, cara, todo depende del juez). Pirámide: muchos hard, algunos soft, pocos subjetivos.
- Construir el golden dataset una vez y **olvidarlo** (deja de ser representativo → tests verdes y producción fallando).

## Lo que NO cubre (sesión 15 / LLMOps)
Métricas RAG (RAGAS), regression tests en CI/CD que bloquean merge, monitoring en producción (Langfuse/Logfire), red teaming (Promptfoo), datasets sintéticos.

## Recursos
- DeepEval (GEval, datasets) · Eugene Yan — task-specific evals · RAGAS · Promptfoo
