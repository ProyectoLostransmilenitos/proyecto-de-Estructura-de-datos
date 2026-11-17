# Planeador de viajes TransMilenio: motor

## Cómo arrancar la app
Un solo comando, desde la carpeta raíz (no necesita instalar nada, solo Python 3):

```
python front/app.py
```
Abre http://127.0.0.1:8000 (puerto distinto: `python front/app.py 8080`).

En **GitHub Pages**, el workflow genera `network.json` a partir de los CSV y publica un adaptador JavaScript sin dependencias. La página lo usa automáticamente cuando no encuentra la API de Python. Permite consultar estaciones, planear viajes, ver buses y horarios, editar la red y simular la fila. Los cambios de la red se mantienen durante esa sesión de la página; las estaciones añadidas se restauran con el almacenamiento local que ya usa la interfaz.

La pestaña **Rendimiento** mide el motor de Python y requiere arrancar la aplicación localmente con el comando anterior. GitHub Pages muestra esta indicación en lugar de intentar ejecutar esas mediciones.

Para comprobar la versión estática antes de publicar:

```sh
mkdir -p /tmp/transmilenio-pages
cp front/index.html front/static-api.mjs /tmp/transmilenio-pages/
python front/export_static.py /tmp/transmilenio-pages/network.json
python -m http.server 8080 --directory /tmp/transmilenio-pages
```

Abre http://127.0.0.1:8080. Al publicar los cambios, espera que termine el workflow de Pages y recarga la página.

Otros comandos:
- Pruebas: `python -m unittest discover -s tests -v`
- Revisar que `motor/` no use nada prohibido: `python verificar_prohibidos.py`
- Mediciones en consola (R11): `python medir.py` (el panel de la app hace lo mismo en la pestaña Rendimiento)

## Carpetas
- `motor/`: el motor (R1 a R10). Todas las reglas del sistema viven aquí.
- `datos/`: `estaciones.csv`, `rutas.csv`, `horarios.csv`.
- `front/`: app web (servidor `app.py` + `index.html`) y panel de rendimiento. Solo llama al motor.

## Supuestos (ajustar si el enunciado dice otra cosa)
Formatos de retorno que el enunciado define y aqui se asumieron. Todos viven en `motor/red.py` y `motor/fila.py`:
- `estado(nombre)` -> `"abierta"`, `"cerrada"` o `"no existe"`.
- `autocompletar` / `rango` -> lista de nombres; `rango` incluye ambos extremos; si `hasta < desde`, lista vacia.
- `proximo_bus` -> `"HH:MM"` de la primera salida **>=** la hora pedida, o `None`.
- `ranking(k)` -> `[(nombre, buses_al_dia), ...]`; empates en orden alfabetico.
- `viaje` -> `{"tipo", "tramos": [(ruta, sube, baja), ...], "paradas", "transbordo"}` o `None`.
- `simular_fila` -> `[(hora_salida, [ids que subieron]), ...]`; los buses salen en `frecuencia, 2*frecuencia, ...`.
- `agregar_parada(ruta, nueva, despues_de)` / `quitar_parada` / `cerrar` / `reabrir` / `deshacer` / `rehacer` -> `True` si hicieron algo, `False` si no (y entonces no entran al historial).

## R12: decisiones por requisito
`n` = estaciones salvo que se diga otra cosa.

| Req | Estructura / algoritmo | Alternativa descartada y por que | Complejidad |
|---|---|---|---|
| R1 estado | `dict` nombre -> abierta | Busqueda binaria en arreglo ordenado: O(log n) cuando el dict da O(1) y es la consulta mas frecuente | O(1) |
| R2 autocompletar | AVL (arbol binario balanceado) de estaciones abiertas; se baja hasta el primer nombre >= prefijo y se recorre en orden hasta k o hasta que deje de coincidir | Recorrer todo el dict y ordenar: O(n log n) por tecla | O(log n + k) |
| R3 rango | Mismo AVL: se baja hasta `desde` y se recorre en orden hasta pasar `hasta` | Filtrar todas y ordenar: O(n log n) | O(log n + m), m = resultados |
| R4 proximo_bus | `dict` (ruta, estacion) -> lista de minutos ordenada (merge sort propio al cargar) + busqueda binaria propia | Recorrer la lista: O(h) con cientos de pasos al dia | O(log h), h = buses al dia de esa ruta en esa estacion |
| R5 viaje | Recorrer hacia adelante cada ruta que sale del origen; en cada parada abierta probar las rutas que pasan por ahi y llegan al destino. Gana el menor numero de paradas (solo cuentan estaciones abiertas); empate: menos transbordos, luego orden alfabetico | BFS con cola sobre todo el grafo: explora de mas porque el limite es un solo transbordo | O(L * r * L), L = paradas por ruta, r = rutas por estacion (no depende de n) |
| R6 ranking | Segundo AVL con clave `(-buses, nombre)`, siempre al dia: cierre, reapertura y edicion lo actualizan en O(log n) | Recalcular y ordenar en cada consulta: O(n log n) cuando se consulta mucho y cambia poco; cache con invalidacion: complica el codigo | consulta O(log n + k); actualizar O(log n) |
| R7 editar rutas | Lista doblemente enlazada por ruta + `dict` estacion -> nodo. Insertar y quitar tocan solo los enlaces vecinos; recorrer al reves usa los punteros `ant` | Arreglo: insertar en el medio mueve L elementos; buscar el nodo con `.index()` esta prohibido | agregar/quitar O(1); recorrido O(L), L = paradas de la ruta |
| R8 cerrar/reabrir | Bandera en el `dict` + quitar/insertar la estacion en los dos AVL (por eso desaparece de R2, R3 y R6). R4 y R5 consultan la bandera | Filtrar la bandera en cada consulta: R2/R3/R6 pagarian O(n) | O(log n) |
| R9 deshacer/rehacer | Dos pilas enlazadas de cambios. Deshacer aplica el inverso (quitar la parada se deshace insertando tras la parada anterior guardada). Un cambio nuevo vacia la pila de rehacer | Guardar copias de toda la red: O(n) por cambio y memoria enorme | O(1) apilar/desapilar; el inverso cuesta lo mismo que la operacion |
| R10 fila de abordaje | Cola enlazada: llegan los pasajeros hasta cada salida y suben hasta llenar el cupo en orden de llegada | Arreglo con `pop(0)`: O(P) por pasajero, P^2 en total | O(P + B), P = pasajeros, B = buses |

Otras decisiones:
- **Horas >= 24:00** (ej. `25:10`): se guardan como minutos desde el inicio del dia de servicio (1510) y se devuelven en el mismo formato. No se envuelven al dia siguiente. Despues del ultimo bus, `proximo_bus` devuelve `None`.
- **Carga**: ordenar cada lista de horarios cuesta O(N log N) una sola vez, con N = filas de `horarios.csv`; si ya viene ordenada solo se verifica en O(N). Las filas con estaciones desconocidas o paradas repetidas en una ruta se ignoran.
- **Ranking al editar rutas**: quitar una parada resta los buses de esa ruta en esa estacion; una parada nueva suma 0 (no se inventan horarios). Deshacer devuelve los buses.
- **recorrido** muestra todas las paradas, tambien las cerradas (vista del operador). Los viajes si se saltan las cerradas.

## R11: mediciones (`python medir.py`)
Tiempo al duplicar n (redes sinteticas de 1.000 a 16.000 estaciones; R10 de 100.000 a 800.000 pasajeros). Si fuera O(1) o logaritmico, la razon es ~1; si fuera lineal, ~2.

| Operacion | Esperado | Razon al duplicar |
|---|---|---|
| R1 estado | O(1) | 0.96 1.08 1.01 1.18 |
| R2 autocompletar | O(log n + k) | 1.15 1.38 1.48 1.18 |
| R3 rango | O(log n + m) | 0.99 1.05 0.99 1.02 |
| R4 proximo_bus | O(log h) | 0.96 1.07 1.16 1.41 |
| R6 ranking | O(log n + k) | 0.96 1.06 1.05 0.99 |
| R7 agregar+quitar | O(1) | 1.09 1.14 1.10 1.19 |
| R8 cerrar+reabrir | O(log n) | 1.08 1.14 1.10 1.19 |
| R9 deshacer+rehacer | O(log n) | 1.10 1.11 1.15 1.07 |
| R10 simular_fila | O(P + B) | 1.97 2.01 2.01 |

Las razones un poco sobre 1 (hasta ~1.5 en R2 y R4) vienen de la memoria cache del procesador al crecer los arboles y los diccionarios, no de un crecimiento lineal: ninguna operacion se acerca a 2. R5 no se mide.

## Estructura
```
front/                app web (R1-R11 con interfaz)
motor/estructuras.py  Pila, Cola, ListaDoble, AVL
motor/algoritmos.py   merge sort y busqueda binaria
motor/carga.py        lectura de los 3 CSV (modulo csv)
motor/red.py          clase Red (R1-R9)
motor/fila.py         simular_fila (R10)
tests/                pruebas contra fuerza bruta
medir.py              panel de rendimiento (R11)
datos/                CSV del proyecto
```
