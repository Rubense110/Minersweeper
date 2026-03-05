# Planteamiento de frontend

Debe tener una barra de navegación que contendrá todos los elementos de la app, salvo que se especifique

Contendrá un formulario para iniciar el proceso de optimizacion del descubrimiento con estos campos:
- Log (Lista automaticamente los disponibles en el servicio, concretamente en el volumen)
- Métricas (Selección entre las métricas disponibles, pueden ponerse todas, algunas, una, etc, en cualquier orden)
- Max evaluations y population size.
- Workers (Usando el sistema actual que autodetecta)

Tras el formulario se manará automáticamente a una página de desglose de resultados que muestre. Los datos se sacan de la BBDD:
- Soluciones (De manera similar a ahora), la vista es general de todas las soluciones, pero al pulsar en una se mostrarán los detalles individuales de ella (ver modelos de datos)
- Esto no está en la navbar evidentemente

Debe haber una página de historial (accesible en navbar) que nos permita revisitar los experimentos pasados mostrando los resultados en la misma pagina que definimos inmediatamente antes.

