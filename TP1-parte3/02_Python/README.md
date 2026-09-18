# Babuinos en conflicto — Cruce del cañón (Python)

Simulación del cruce de babuinos por una cuerda que soporta como máximo 5
a la vez y donde dos babuinos en direcciones opuestas se pelean hasta que
uno cae. **Cada babuino es un hilo**, y una clase `Cuerda` (un monitor)
garantiza que **nunca** haya dos direcciones a la vez en la cuerda, que
**nunca** haya más de 5, y que **nadie espere indefinidamente**.

## Decisiones de diseño

El enunciado deja varios puntos abiertos; estas son las decisiones que
tomamos y por qué.

**Lenguaje: Python.** Para esta parte 3 quisimos usar un lenguaje distinto
por enunciado (Carga Criolla en Java, Babuinos en Python, Baño compartido
en C++). `threading.Condition` es un monitor casi directo, así que el
algoritmo se escribe y verifica rápido. El GIL no molesta: los hilos
esperan, no calculan.

**"Garantizar que ninguno muera".** Lo interpretamos como que la pelea
**nunca debe ocurrir**: el programa no la simula, la evita. Eso equivale
a dos reglas que la cuerda hace cumplir siempre: (1) en la cuerda solo hay
babuinos de **una** dirección a la vez y (2) hay **como máximo 5**.

**Política de acceso: FIFO estricta por número de turno.**
- Cada babuino toma un turno al llegar (dentro del candado del monitor) y
  solo sube cuando (a) le toca el turno y (b) la cuerda está vacía, o va
  en su misma dirección y tiene lugar.
- **Ventaja:** garantiza que no haya inanición. Un babuino con el turno *t*
  solo espera a los *t* que llegaron antes; ningún lado puede quedar
  postergado para siempre.
- **Costo:** si el que sigue en la fila va en dirección contraria, frena a
  los de atrás (aunque vayan en la dirección que está cruzando) hasta que
  la cuerda se vacíe. Es menos eficiente que darle prioridad a la
  dirección en curso, pero esa alternativa puede dejar esperando al otro
  lado indefinidamente, y elegimos garantizar el avance de todos.
- **Por qué el turno lo garantizamos nosotros:** ni `threading.Semaphore`
  ni `Lock` prometen orden de espera FIFO, y justo eso es lo que evita la
  inanición. Con un número de turno el orden queda garantizado por diseño,
  no por la implementación del lenguaje.

**Sin deadlock.** Hay un solo recurso (la cuerda) y un solo candado.
`Condition.wait_for` libera el candado mientras espera, así que nadie
retiene algo mientras aguarda otra cosa.

**Población.** Se ejecuta con `<izquierda> <derecha>`: cuántos babuinos
parten de cada lado (los de la izquierda cruzan hacia la derecha, y
viceversa). Su orden de llegada es al azar (0 a 1 s) y cada cruce dura
entre 0,1 y 0,3 s. Los tiempos son reales, sin escala.

**Verificación independiente.** El `Auditor` (Observer) **no le pregunta
nada a la cuerda**: recibe cada evento (sube, baja) y recalcula por su
cuenta cuántos hay y en qué dirección. Así, si la cuerda tuviera un error,
el auditor lo detecta y no lo repite. Informa: babuinos que cruzaron por
lado, máximo simultáneo, peleas, cuerdas rotas e ingresos fuera de turno.

**Patrones de diseño.**
- **Observer** (`ObservadorCuerda`): `RegistroConsola` (el log) y `Auditor`
  reciben los mismos eventos sin que la cuerda sepa qué hacen con ellos.
- **Factory Method** (`FabricaBabuinos`): crea toda la tropa, con su
  dirección y sus tiempos, en un solo hilo antes de arrancar.

**Reglas de la cátedra.** Constantes con nombre en `constantes.py` (sin
números mágicos), funciones de hasta 15 líneas y Google Python Style.

## Estructura

| Módulo | Responsabilidad |
|---|---|
| `main.py` | Lee `<izquierda> <derecha>`, corre la simulación e imprime el informe |
| `simulacion.py` | Arma la cuerda y la tropa, lanza un hilo por babuino y espera con `join()` |
| `cuerda.py` | **Monitor**: admisión FIFO por turno, dirección única y capacidad 5 |
| `babuino.py` | El hilo: llega, entra, cruza, sale |
| `fabrica.py` | Factory Method de la tropa |
| `observadores.py` | Observer: `RegistroConsola` y `Auditor` (+ `InformeAuditoria`) |
| `eventos.py`, `direccion.py`, `constantes.py` | Datos y parámetros |
| `scripts/verificar.py` | Pruebas de estrés y validación del auditor |

## Cómo correrlo

Desde VS Code (con la carpeta del repo abierta), paleta de comandos →
*Run Task*:

- **"Babuinos: correr simulación (8 izquierda, 6 derecha)"**
- **"Babuinos: verificar (pruebas de estrés)"**

O por línea de comandos, parado en esta carpeta:

```bash
python src/main.py 8 6          # <izquierda> <derecha>
python scripts/verificar.py
```

### Ejemplo de salida (8 babuinos hacia la derecha, 6 hacia la izquierda)

```
[      5 ms] Babuino 12 (<-) | llega y toma el turno 0
[      5 ms] Babuino 12 (<-) | sube a la cuerda (en cuerda: 1, hacia la izquierda)
[     14 ms] Babuino 03 (<-) | llega y toma el turno 1
[     14 ms] Babuino 03 (<-) | sube a la cuerda (en cuerda: 2, hacia la izquierda)
[     51 ms] Babuino 02 (->) | llega y toma el turno 2
[    124 ms] Babuino 12 (<-) | baja de la cuerda (en cuerda: 1)
[    154 ms] Babuino 03 (<-) | baja de la cuerda (en cuerda: 0)
[    154 ms] Babuino 02 (->) | sube a la cuerda (en cuerda: 1, hacia la derecha)
...
Cruzaron 14 de 14 babuinos (8 hacia la derecha, 6 hacia la izquierda)
Máximo simultáneo en la cuerda: 4 (límite 5)
Peleas (direcciones opuestas a la vez): 0
Cuerdas rotas (más de 5): 0
Ingresos fuera de turno: 0
```

El Babuino 02 (→) llegó con dos babuinos (←) todavía en la cuerda, así que
esperó a que bajaran los dos antes de subir: nunca compartieron la cuerda.

## Verificación

`scripts/verificar.py` comprime los tiempos (×0,05) para forzar mucha más
contención que una corrida normal, y comprueba dos cosas:

1. **La cuerda real aguanta.** 8 configuraciones × 10 repeticiones (desde 1
   babuino hasta 60 de cada lado, incluidos los casos extremos "todos del
   mismo lado"): en todas, cruzaron todos, sin peleas, sin cuerdas rotas y
   sin ingresos fuera de turno. Además se llega a **5 babuinos a la vez**
   sin pasarse, o sea que el límite se ejercita de verdad.
2. **El auditor sirve.** Se le pasan dos cuerdas defectuosas a propósito (una
   sin control de dirección y otra sin límite de capacidad) y el auditor
   detecta las peleas y las roturas respectivamente. Sin esta prueba, un
   auditor que siempre dijera "todo bien" pasaría desapercibido.
