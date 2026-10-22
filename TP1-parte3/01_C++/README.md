# Baño compartido (C++)

Simulación de un único baño con capacidad para 3 empleados, donde **nunca
puede haber hombres y mujeres al mismo tiempo**. **Cada empleado es un
hilo** (`std::thread`) y una clase `Bano` (un monitor) garantiza que
**nunca** se mezclen, que **nunca** haya más de 3 y que **nadie espere
indefinidamente**.

Es el mismo problema que *Babuinos en conflicto* (dos grupos que no se
pueden mezclar y una capacidad limitada), con otros números. Reutilizamos
el diseño ya verificado en Python, pero en C++ y con un patrón distinto
(ver más abajo).

## Decisiones de diseño

El enunciado deja varios puntos abiertos; estas son las decisiones que
tomamos y por qué.

**Lenguaje: C++.** Para esta parte 3 usamos un lenguaje distinto por
enunciado (Carga Criolla en Java, Babuinos en Python, Baño en C++). Como
el algoritmo ya estaba validado, traducirlo era de bajo riesgo, y C++
nos obliga a construir a mano lo que Java da hecho (ver el turno FIFO).

**Reglas que hace cumplir el baño.** Siempre, sin excepción: (1) adentro
hay solo un sexo a la vez y (2) hay como máximo 3 personas.

**Política de acceso: FIFO estricta por número de turno.**
- Cada empleado toma un turno al llegar (dentro del candado del monitor)
  y solo entra cuando le toca y el baño lo admite: está vacío, o lo
  ocupa su mismo sexo y hay lugar.
- **Ventaja:** garantiza que no haya inanición. Un empleado con el turno
  *t* solo espera a los *t* que llegaron antes.
- **Costo:** si el que sigue en la fila es del otro sexo, frena a los de
  atrás (aunque sean del sexo que está adentro) hasta que el baño se
  vacíe. Es menos eficiente que darle prioridad al grupo que ya está
  adentro, pero esa alternativa puede dejar esperando al otro grupo
  indefinidamente.
- **Por qué el turno lo garantizamos nosotros:** ni `std::mutex` ni
  `std::counting_semaphore` prometen orden de espera FIFO, y justo eso es
  lo que evita la inanición.

**Sin deadlock.** Hay un solo recurso (el baño) y un solo candado.
`condition_variable::wait` libera el candado mientras espera, así que
nadie retiene algo mientras aguarda otra cosa.

**Población.** Se ejecuta con `<hombres> <mujeres>`. El orden de llegada
es al azar (0 a 1 s) y cada uso dura entre 0,1 y 0,3 s, en tiempo real.

**Verificación independiente.** El `Auditor` (Observer) **no le pregunta
nada al baño**: recibe cada evento (entra, sale) y recalcula por su
cuenta cuántos hay y de qué sexo. Informa quiénes usaron el baño, el
máximo simultáneo, las mezclas, los excesos de capacidad y los ingresos
fuera de turno.

**Patrones de diseño.**
- **Strategy** (`IPoliticaAdmision`): decide si un empleado puede entrar
  ahora. La real es `PoliticaFifoEstricta`. Es la diferencia con la
  versión de Python: la regla de admisión está separada del monitor, así
  que en las pruebas se enchufa una política defectuosa sin tocar `Bano`.
- **Observer** (`IObservador`): `RegistroConsola` (el log) y `Auditor`
  reciben los mismos eventos sin que el baño sepa qué hacen con ellos.
- **Factory Method** (`FabricaEmpleados`): crea toda la plantilla, con su
  sexo y sus tiempos, en un solo hilo antes de arrancar.

**Reglas de la cátedra.** Constantes con nombre en `constantes.h` (sin
números mágicos), funciones de hasta 15 líneas, y el `.clang-format` del
repo (Google con llaves Allman, 180 columnas). Compila con
`-Wall -Wextra` sin advertencias.

## Estructura

| Archivo | Responsabilidad |
|---|---|
| `src/main.cpp` | Lee `<hombres> <mujeres>`, corre la simulación e imprime el informe |
| `src/simulacion.*` | Arma el baño y la plantilla, lanza un hilo por empleado y espera con `join()` |
| `src/bano.*` | **Monitor**: turno FIFO y notificación a los observadores |
| `src/politica_admision.*` | Strategy: `IPoliticaAdmision` y `PoliticaFifoEstricta` |
| `src/empleado.*` | El hilo: llega, entra, usa, sale |
| `src/fabrica_empleados.*` | Factory Method de la plantilla |
| `src/observador.*` | Observer: `RegistroConsola` y `Auditor` (+ `InformeAuditoria`) |
| `src/evento.h`, `sexo.h`, `reloj.*`, `constantes.h` | Datos y parámetros |
| `tests/verificar.cpp` | Pruebas de estrés y validación del auditor |
| `scripts/ejecutar.py` | Compila y ejecuta (en una carpeta local[^1]) |

## Cómo correrlo

Desde VS Code (con la carpeta del repo abierta), paleta de comandos →
*Run Task*:

- **"Baño: correr simulación (8 hombres, 6 mujeres)"**
- **"Baño: verificar (pruebas de estrés)"**

O por línea de comandos, parado en esta carpeta (compila y ejecuta):

```bash
python scripts/ejecutar.py bano 8 6      # <hombres> <mujeres>
python scripts/ejecutar.py verificar
```

### Ejemplo de salida (8 hombres, 6 mujeres)

La salida no lleva acentos para verse bien en la consola de Windows.
`(H)` es hombre y `(M)` mujer.

```
[     47 ms] Empleado 13 (M) | llega y toma el turno 0
[     47 ms] Empleado 13 (M) | entra al bano (adentro: 1, mujeres)
[     62 ms] Empleado 01 (H) | llega y toma el turno 1
[    109 ms] Empleado 12 (M) | llega y toma el turno 2
[    154 ms] Empleado 11 (M) | llega y toma el turno 3
[    201 ms] Empleado 13 (M) | sale del bano (adentro: 0)
[    201 ms] Empleado 01 (H) | entra al bano (adentro: 1, hombres)
...
[    402 ms] Empleado 01 (H) | sale del bano (adentro: 0)
[    402 ms] Empleado 12 (M) | entra al bano (adentro: 1, mujeres)
[    402 ms] Empleado 11 (M) | entra al bano (adentro: 2, mujeres)
...
Usaron el bano 14 de 14 empleados (8 hombres, 6 mujeres)
Maximo simultaneo dentro del bano: 3 (limite 3)
Mezclas hombres/mujeres: 0
Excesos de capacidad (mas de 3): 0
Ingresos fuera de turno: 0
```

Los empleados 12 y 11 (M) llegaron después que el 01 (H), así que
respetaron el orden: el 01 entró apenas salió la 13, y las dos recién
entraron cuando él salió (402 ms). Nunca compartieron el baño con él.

## Verificación

`tests/verificar.cpp` comprime los tiempos (×0,05) para forzar mucha más
contención que una corrida normal, y comprueba dos cosas:

1. **El baño real aguanta.** 8 configuraciones × 10 repeticiones (desde 1
   empleado hasta 60 de cada sexo, incluidos los casos extremos "todos del
   mismo sexo"): en todas usaron el baño todos, sin mezclas, sin excesos
   de capacidad y sin ingresos fuera de turno. Además se llega a **3
   adentro** sin pasarse, o sea que el límite se ejercita de verdad.
2. **El auditor sirve.** Se le pasan dos políticas defectuosas a propósito
   (una sin control de sexo y otra sin límite de capacidad) y el auditor
   detecta las mezclas y los excesos respectivamente. Sin esta prueba, un
   auditor que siempre dijera "todo bien" pasaría desapercibido.

---

[^1]: Se compila y se corre en `%LOCALAPPDATA%\bano_build`, no dentro de
OneDrive, porque en el TP de Naruto los binarios ejecutados con el
directorio de trabajo dentro de OneDrive se cerraban inesperadamente. En
este TP no se vio ese problema, pero mantenemos la misma práctica por
consistencia.
