import argparse
from multiprocessing import Lock, Queue
from multiprocessing.queues import Queue as QueueType
from typing import Any, Dict, List

from fabrica_sistemas_vigilancia import FabricaSistemasVigilancia
from sistema_vigilancia import SistemaVigilancia

_DURACION_POR_DEFECTO_SEGUNDOS = 30.0
_FRECUENCIA_POR_DEFECTO_SEGUNDOS = 2.0


def parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitoreo concurrente de las zonas de Jurassic Park."
    )
    parser.add_argument(
        "--duracion",
        type=float,
        default=_DURACION_POR_DEFECTO_SEGUNDOS,
        help="Duración total del monitoreo, en segundos.",
    )
    parser.add_argument(
        "--frecuencia",
        type=float,
        default=_FRECUENCIA_POR_DEFECTO_SEGUNDOS,
        help="Frecuencia de reporte de cada zona, en segundos.",
    )
    return parser.parse_args()


def anunciar_inicio(duracion_seg: float, frecuencia_seg: float) -> None:
    print(
        f"Iniciando monitoreo del parque durante {duracion_seg:.0f} "
        f"segundos (reportes cada {frecuencia_seg:.0f} segundos)...\n"
    )


def iniciar_todos(sistemas: List[SistemaVigilancia]) -> None:
    for sistema in sistemas:
        sistema.start()


def esperar_a_todos(sistemas: List[SistemaVigilancia]) -> None:
    for sistema in sistemas:
        sistema.join()


def recolectar_resultados(
    cola_resultados: QueueType, cantidad: int
) -> List[Dict[str, Any]]:
    return [cola_resultados.get() for _ in range(cantidad)]


def mostrar_resumen_general(resultados: List[Dict[str, Any]]) -> None:
    total_eventos = sum(r["total_eventos"] for r in resultados)
    total_criticos = sum(r["total_criticos"] for r in resultados)
    print("Monitoreo finalizado. Resumen general:\n")
    print(f"Total de eventos detectados en el parque: {total_eventos}")
    print(f"Total de eventos críticos en el parque:    {total_criticos}")


def main() -> None:
    args = parsear_argumentos()
    lock_impresion = Lock()
    cola_resultados: QueueType = Queue()

    sistemas = FabricaSistemasVigilancia.crear_todos(
        args.duracion, args.frecuencia, lock_impresion, cola_resultados
    )

    anunciar_inicio(args.duracion, args.frecuencia)
    iniciar_todos(sistemas)
    esperar_a_todos(sistemas)

    resultados = recolectar_resultados(cola_resultados, len(sistemas))
    mostrar_resumen_general(resultados)


if __name__ == "__main__":
    main()
