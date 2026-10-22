# Ejercicio 1 - Árbol de procesos en Java

## Problema que resuelve

Generar el siguiente árbol de procesos del sistema operativo:

```
              A
              |
              B
            /   \
           C     D
           |    / \
           E   F   G
          / \
         H   I
```

Cada proceso debe crear a sus hijos de forma **concurrente**: no es válido
crear un hijo y esperar a que termine antes de crear al siguiente.

## Por qué se resolvió así

Un mismo programa (`NodeProcess`) se reutiliza para representar **cualquier**
nodo del árbol: recibe su propio nombre por parámetro y, a partir de ahí,
sabe qué hijos le corresponden. Esto evita escribir 9 programas distintos
(uno por letra) y refleja cómo funciona `fork()` en C: el código es el
mismo, lo único que cambia es el dato con el que cada proceso decide qué
camino tomar.

Se usaron tres patrones de diseño:

- **Composite** (`NodoProceso` / `NodoHoja` / `NodoInterno`): un nodo hoja
  (sin hijos) y un nodo interno (con hijos) se tratan de forma uniforme a
  través del método `ejecutar()`, sin que el resto del programa necesite
  distinguirlos.
- **Factory Method** (`NodoProcesoFactory`): decide si hay que construir
  una hoja o un nodo interno según lo que informa `ProcessTree`, en vez de
  que esa decisión esté repartida por el código.
- **Builder** (`ProcessBuilder`, del propio JDK): configura y lanza cada
  proceso hijo del sistema operativo.

## Funcionamiento del código

| Archivo | Rol |
|---|---|
| `ProcessTree.java` | Única fuente de verdad: mapa nombre → lista de hijos. |
| `NodoProceso.java` | Clase base: imprime PID propio y PID del padre, e informa la finalización. |
| `NodoHoja.java` | Nodo sin hijos: se queda 15 segundos "vivo" antes de terminar, para poder verificar el árbol desde afuera mientras corre. |
| `NodoInterno.java` | Nodo con hijos: los lanza a **todos** con `start()` antes de esperar a ninguno, y recién después los espera con `waitFor()` uno por uno. |
| `NodoProcesoFactory.java` | Construye una `NodoHoja` o un `NodoInterno` según corresponda. |
| `NodeProcess.java` | Punto de entrada: lee el nombre del nodo por argumento y delega en la fábrica. |

Flujo: `NodeProcess` recibe su nombre → `NodoProcesoFactory` decide qué tipo
de nodo es → si tiene hijos, los crea todos primero y espera después
(garantiza la concurrencia); si es hoja, hace la pausa de verificación.

## Cómo se ejecuta

```bash
javac -d out src/procesos/*.java
java -cp out procesos.NodeProcess A
```

Esto arranca todo el árbol desde el nodo A. Mientras los nodos hoja (F, G,
H, I) están en la pausa de 15 segundos, se puede verificar el árbol desde
otra terminal, por ejemplo en PowerShell:

```powershell
Get-CimInstance Win32_Process -Filter "Name='java.exe'" | Select-Object ProcessId, ParentProcessId, @{N='Nodo';E={($_.CommandLine -split '\s+')[-1]}} | Sort-Object ParentProcessId, ProcessId | Format-Table -AutoSize
```

(en Linux/Mac: `ps --forest -o pid,ppid,cmd`)
