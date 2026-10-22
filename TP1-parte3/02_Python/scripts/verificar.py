"""Pruebas de estrés del cruce de babuinos.

Comprueba dos cosas:
1. La cuerda real nunca deja que se crucen, la rompan o entren fuera de turno, aun con
   muchos babuinos y tiempos muy comprimidos (mucha más contención que la corrida normal).
2. El auditor de verdad detecta los errores: se le pasan dos cuerdas defectuosas a propósito
   (sin control de dirección y sin límite de capacidad) y tiene que dar la alarma.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from constantes import CAPACIDAD_CUERDA  # noqa: E402
from cuerda import Cuerda  # noqa: E402
from simulacion import simular  # noqa: E402

ESCALA_RAPIDA = 0.05
REPETICIONES = 10
INTENTOS_DETECCION = 10
CONFIGURACIONES = [(1, 0), (0, 1), (5, 5), (8, 6), (0, 40), (40, 0), (25, 25), (60, 60)]
CODIGO_ERROR = 1


class CuerdaSinControlDeDireccion(Cuerda):
    """Defectuosa: deja subir a cualquiera mientras haya lugar (los babuinos se cruzan)."""

    def _puede_subir(self, turno, direccion):
        return turno == self._turno_que_puede_subir and self._en_cuerda < CAPACIDAD_CUERDA


class CuerdaSinLimiteDeCapacidad(Cuerda):
    """Defectuosa: no cuenta cuántos hay en la cuerda (se rompe)."""

    def _puede_subir(self, turno, direccion):
        return turno == self._turno_que_puede_subir and (self._en_cuerda == 0 or self._direccion is direccion)


def verificar_configuracion(izquierda, derecha):
    """Corre la configuración varias veces. Devuelve (todo_ok, maximo_simultaneo_visto)."""
    todo_ok, maximo = True, 0
    for _ in range(REPETICIONES):
        informe = simular(izquierda, derecha, escala_tiempo=ESCALA_RAPIDA)
        maximo = max(maximo, informe.maximo_simultaneo)
        todo_ok = todo_ok and informe.es_correcto() and informe.total_cruzaron == izquierda + derecha
    return todo_ok, maximo


def el_auditor_detecta(clase_cuerda, izquierda, derecha, campo_de_error):
    """True si, en algún intento, el auditor marca el error esperado con la cuerda defectuosa."""
    for _ in range(INTENTOS_DETECCION):
        informe = simular(izquierda, derecha, escala_tiempo=ESCALA_RAPIDA, clase_cuerda=clase_cuerda)
        if getattr(informe, campo_de_error) > 0:
            return True
    return False


def verificar_cuerda_real():
    todo_ok, maximo_global = True, 0
    for izquierda, derecha in CONFIGURACIONES:
        ok, maximo = verificar_configuracion(izquierda, derecha)
        maximo_global = max(maximo_global, maximo)
        todo_ok = todo_ok and ok
        print(f"  {izquierda:>2} izquierda / {derecha:>2} derecha x{REPETICIONES}: {'OK' if ok else 'FALLA'} (máximo en cuerda: {maximo})")
    alcanzo_capacidad = maximo_global == CAPACIDAD_CUERDA
    print(f"  Se llegó a la capacidad máxima ({CAPACIDAD_CUERDA}) sin pasarse: {'sí' if alcanzo_capacidad else 'NO'}")
    return todo_ok and alcanzo_capacidad


def verificar_auditor():
    detecta_peleas = el_auditor_detecta(CuerdaSinControlDeDireccion, 20, 20, "peleas")
    detecta_roturas = el_auditor_detecta(CuerdaSinLimiteDeCapacidad, 0, 60, "cuerdas_rotas")
    print(f"  Cuerda sin control de dirección -> el auditor detecta peleas: {'sí' if detecta_peleas else 'NO'}")
    print(f"  Cuerda sin límite de capacidad  -> el auditor detecta roturas: {'sí' if detecta_roturas else 'NO'}")
    return detecta_peleas and detecta_roturas


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("1) Cuerda real bajo estrés")
    cuerda_ok = verificar_cuerda_real()
    print("2) El auditor detecta cuerdas defectuosas")
    auditor_ok = verificar_auditor()
    print("\nRESULTADO:", "TODO OK" if cuerda_ok and auditor_ok else "HAY FALLAS")
    return 0 if cuerda_ok and auditor_ok else CODIGO_ERROR


if __name__ == "__main__":
    sys.exit(main())
