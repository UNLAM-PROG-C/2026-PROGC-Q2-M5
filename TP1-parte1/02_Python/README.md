# Ejercicio 2 - Monitoreo concurrente de Jurassic Park (Python)

## Problema que resuelve

El parque tiene 5 zonas (Área de Velociraptores, Sector del Tiranosaurio,
Recinto de los Triceratops, Centro de Visitantes, Laboratorio Genético),
cada una con su propio sistema de vigilancia. Cada sistema debe monitorear
**exclusivamente** su zona, ejecutando de forma **concurrente** con el
resto, y cada cierto intervalo debe reportar un evento aleatorio (según
probabilidades definidas por zona). Al finalizar el tiempo total de
monitoreo, cada sistema informa cuántos eventos detectó en total y cuántos
de esos fueron críticos.

## Por qué se resolvió así

Cada zona se vigila con un **proceso real del sistema operativo**
(`multiprocessing.Process`), no con un hilo: así cada zona tiene su propia
memoria y su propio PID, y la concurrencia es real (no limitada por el GIL
de Python). Como los procesos no comparten memoria, cada uno le devuelve su
resumen final al proceso principal a través de una `Queue` compartida.

Se usaron estos patrones/prácticas de diseño:

- **Strategy** (`selector_eventos.py`): la forma de elegir el próximo
  evento (al azar, ponderado por probabilidad) está separada de
  `SistemaVigilancia` en una clase intercambiable. Permite, por ejemplo,
  reemplazarla por un selector fijo en un test sin tocar el resto.
- **Factory Method** (`fabrica_sistemas_vigilancia.py`): centraliza la
  creación de los 5 procesos de vigilancia, para que `main.py` no conozca
  esos detalles de construcción.
- **Active Object** (`multiprocessing.Process` + `Queue`): cada zona
  encapsula su propio proceso y expone sus resultados de forma
  asincrónica, en vez de compartir memoria directamente.

## Funcionamiento del código

| Archivo | Rol |
|---|---|
| `modelo.py` | Tabla de datos: cada zona con sus posibles eventos, probabilidad y si es crítico. |
| `selector_eventos.py` | Estrategia para elegir el próximo evento a reportar (aleatoria, ponderada por probabilidad). |
| `sistema_vigilancia.py` | El proceso que vigila una sola zona: cada `frecuencia` segundos elige un evento, lo imprime, lo cuenta, y al terminar informa su resumen. |
| `fabrica_sistemas_vigilancia.py` | Crea un `SistemaVigilancia` por cada zona de `modelo.py`. |
| `main.py` | Punto de entrada: lee `--duracion` y `--frecuencia`, arranca **todos** los procesos antes de esperar a ninguno, y al final junta y muestra el resumen general del parque. |

Eventos considerados críticos (según el enunciado): dinosaurio fuera de su
recinto, falla en el cerco eléctrico, pérdida de comunicación y alerta de
seguridad. El resto de los eventos no cuentan como críticos.

## Cómo se ejecuta

```bash
python main.py --duracion 30 --frecuencia 2
```

- `--duracion`: duración total del monitoreo, en segundos (default: 30).
- `--frecuencia`: cada cuántos segundos reporta eventos cada zona (default: 2).

En Windows, si `multiprocessing` no funciona, verificar que la creación de
procesos esté dentro de `if __name__ == "__main__":` (ya está así en
`main.py`), ya que en esa plataforma se usa el método `spawn`.
