package cargacriolla;

import static cargacriolla.Constantes.CANTIDAD_PLANTAS;
import static cargacriolla.Constantes.HORAS_POR_DIA;

/** Resultado de una corrida: el tiempo llega hasta la descarga del ultimo viaje. */
record ResultadoSimulacion(int camiones, int viajesPorPlanta, double horas) {
  double dias() {
    return horas / HORAS_POR_DIA;
  }

  int viajesTotales() {
    return viajesPorPlanta * CANTIDAD_PLANTAS;
  }
}
