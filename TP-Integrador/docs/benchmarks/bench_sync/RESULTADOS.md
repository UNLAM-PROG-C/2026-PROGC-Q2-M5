# Resultados: sincronización en un histograma de luminancia

Problema: el histograma de 256 bins de la luminancia que calcula el efecto
noche, sobre un cuadro RGB de 720p (921.600 píxeles) o 1080p (2.073.600).
Dos escenas: **uniforme** (la luminancia se reparte en los 256 bins) y
**oscura** (canales entre 0 y 7: todo cae en unos 8 bins, máxima
contención). Todos los métodos se comparan contra `numpy.bincount` y los
cinco dieron el histograma exacto en los cuatro casos.

## Hardware y versiones

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 5090, capacidad 12.0, 170 SM |
| Driver | 32.0.16.1088 (CUDA 13.3 según el driver), nvcc 13.5 |
| CPU | AMD Ryzen 9 9950X3D, 16 núcleos / 32 hilos |
| Sistema | Windows 11 (10.0.26200) |
| Software | Python 3.12.10 (con GIL), NumPy 2.5.4, PyCUDA 2026.1 |

Lanzamiento GPU: 256 hilos por bloque, 170 × 4 = 680 bloques, bucle
*grid-stride*; es igual para todos los kernels, así solo cambia la
sincronización. CPU: 8 hilos (`threading`), 4 procesos en la demo de carrera.

## Tiempos (mediana, en ms)

N: 200 lanzamientos para el kernel solo (eventos CUDA), 50 ciclos completos
de 5 pasos (reservar, subir, kernel, bajar, liberar), 3 corridas de (d),
5 de (e) y 30 de (f).

| Caso | (a) global kernel | (b) shared kernel | (a) 5 pasos | (b) 5 pasos | (d) lock | (e) privado | (f) bincount |
|---|---:|---:|---:|---:|---:|---:|---:|
| 720p uniforme | 0,1315 | 0,0146 | 0,705 | 0,593 | 84,8 | 24,4 | 5,34 |
| 720p oscura | 0,1154 | 0,0106 | 0,706 | 0,572 | 87,5 | 25,1 | 5,41 |
| 1080p uniforme | 0,2869 | 0,0148 | 1,053 | 0,766 | 200,0 | 56,3 | 12,39 |
| 1080p oscura | 0,2501 | 0,0105 | 0,998 | 0,770 | 196,4 | 55,9 | 12,56 |

## Speedups

| Caso | (a)/(b) kernel | (a)/(b) 5 pasos | (d)/(e) | (d)/(f) | (f)/(b) kernel | (f)/(b) 5 pasos |
|---|---:|---:|---:|---:|---:|---:|
| 720p uniforme | 9,0× | 1,19× | 3,5× | 15,9× | 367× | 9,0× |
| 720p oscura | 10,9× | 1,23× | 3,5× | 16,2× | 512× | 9,5× |
| 1080p uniforme | 19,4× | 1,37× | 3,6× | 16,1× | 837× | 16,2× |
| 1080p oscura | 23,8× | 1,30× | 3,5× | 15,6× | 1197× | 16,3× |

## Condición de carrera

Mismos cuadros, sin sincronizar. El total debería ser igual al número de
píxeles.

| Caso | GPU sin atómico | Hilos con `+=` sin lock | Procesos con `+=` sin lock |
|---|---:|---:|---:|
| 720p uniforme | 2.842 de 921.600 | 921.600 (exacto) | 913.521 (−0,9 %) |
| 720p oscura | 71 de 921.600 | 921.600 (exacto) | 617.999 (−32,9 %) |
| 1080p uniforme | 5.941 de 2.073.600 | 2.073.600 (exacto) | 2.055.398 (−0,9 %) |
| 1080p oscura | 145 de 2.073.600 | 2.073.600 (exacto) | 1.383.563 (−33,3 %) |

En GPU, `hist[b] = hist[b] + 1` son tres pasos (leer, sumar, escribir):
miles de hilos leen el mismo valor y escriben todos el mismo resultado, así
que se pierde más del 99 % de las cuentas. En CPU, los procesos corren de
verdad en paralelo y pierden cuentas; cuantos menos bins (escena oscura),
más choques. Los hilos dieron exacto por el GIL, no porque `+=` sea seguro.

## Conclusión

1. En GPU conviene (b): el kernel es entre 9 y 24 veces más rápido que (a).
2. En (a) los 2 millones de `atomicAdd` van a solo 256 direcciones de
   memoria global; la memoria los serializa y la contención crece con el
   tamaño del cuadro (de 9× a 19× entre 720p y 1080p).
3. En (b) cada bloque compite solo con sus 256 hilos sobre una copia en
   `__shared__`, que está dentro del SM y es mucho más rápida; a global
   llegan 256 atómicos por bloque (unos 174 mil en vez de 2 millones).
4. Con los 5 pasos la ventaja baja a 1,2–1,4×: subir el cuadro por PCIe
   (unos 0,6 ms) pesa más que el kernel. Conviene cuando el cuadro ya está
   en la GPU, como en el juego.
5. En CPU, el lock por incremento es el más lento: 2 millones de
   `acquire`/`release` y los hilos esperando uno detrás de otro.
6. Privatizar (e) es 3,5× más rápido que (d): un solo lock al final, en el
   merge. Es la misma idea que (b) en la GPU.
7. Aun así (e) no aprovecha los 8 hilos: el GIL deja ejecutar bytecode a
   un hilo por vez, así que los hilos se turnan en vez de correr en paralelo.
8. `numpy.bincount` en un hilo gana a todo lo de CPU (4,5× sobre (e)) porque
   el bucle corre en C, sin intérprete ni lock.
9. El GIL también explica que los hilos sin lock dieran exacto. No es una
   garantía: con procesos, que no comparten GIL, la misma operación pierde
   hasta un tercio de las cuentas.
10. Regla: si muchos actualizan pocos datos compartidos, privatizar y
    combinar al final; atómicos sobre memoria rápida y local cuando hace
    falta, y nunca operaciones de leer-modificar-escribir sin sincronizar.
11. Para el juego: cambiar el `atomicAdd` global del efecto noche por (b)
    ahorraría unos 0,24 ms por cuadro a 1080p.
