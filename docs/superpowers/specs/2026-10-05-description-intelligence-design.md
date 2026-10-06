# Descripciones como fuente de datos

Alcance aprobado: extraer información explícita del título y la descripción, conservar evidencia textual, completar campos ausentes, explicar posibles factores del precio junto con los comparables y mejorar las preguntas al vendedor.

## Datos y procedencia

Extender ListingFacts y description_facts con versión, motor, equipamiento, dueño único, mantenimiento, distribución, cubiertas, uso comercial, reparaciones, daños, VTV, documentación, permuta, negociación, urgencia y motivo de venta. Cada valor nuevo requiere una cita presente en el texto. La ausencia se representa con null o una lista vacía; las afirmaciones son del vendedor, no verificaciones del vehículo. Los campos estructurados conservan prioridad y las contradicciones quedan visibles.

## Flujo

El worker analiza cualquier descripción completa que enriquece, usando el proveedor y el límite diario existentes. Guarda la versión del análisis y una huella de título + descripción para reutilizar resultados. Una transacción con lock de Postgres reserva el presupuesto entre fuentes y pasadas. Ante error o falta de presupuesto, conserva las reglas existentes. No requiere una llamada de IA por visita a la web.

La ficha muestra «Según el vendedor» con citas, «Qué puede influir en el precio» y preguntas específicas. La comparación numérica y el score siguen siendo determinísticos. Los factores se presentan como posibles influencias, sin asignar ajustes monetarios inventados. Sin comparables suficientes se explicita que no se puede evaluar la diferencia.

## Validación y operación

Pruebas con respuestas simuladas: citas inexistentes, negaciones, datos faltantes, contradicciones, cache invalidado por cambios de texto/versión, límite concurrente, fallos del proveedor y precio parcial. Pruebas del contrato JSON, normalización, señales y presentación. No hay llamadas pagas ni modificaciones de datos de producción durante la validación. Un comando de reproceso con dry-run permite revisar avisos anteriores antes de aplicarlos.
