"""Etapa de GENERACIÓN del RAG (sesión 11).

Cierra el pipeline por el lado del generador: recupera contexto (reutilizando el
retrieval de la sesión 10), genera una estimación estructurada con CITACIÓN POR LÍNEA
y verifica que ninguna cita apunte a una fuente que no estaba en el contexto.

Nota de continuidad: el enunciado asume un generador de la "sesión 9 en directo" que en
nuestro repo no existía (hicimos la 9 como diagnóstico). Este módulo es ese generador,
construido sobre nuestro repo (Opción B).
"""
