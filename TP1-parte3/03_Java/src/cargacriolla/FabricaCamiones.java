package cargacriolla;

import static cargacriolla.Constantes.VIAJE_MAXIMO_HORAS;
import static cargacriolla.Constantes.VIAJE_MINIMO_HORAS;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * Factory Method: crea la flota completa en un solo hilo, antes de que arranque la simulacion. Cada
 * chofer recibe su tiempo de viaje fijo, dentro del rango del relevamiento.
 */
final class FabricaCamiones {
  private FabricaCamiones() {}

  static List<Camion> crear(
      int cantidad, Planta plantaInicial, Reloj reloj, ObservadorEstado observador, Random azar) {
    List<Camion> camiones = new ArrayList<>();
    for (int id = 1; id <= cantidad; id++) {
      camiones.add(new Camion(id, crearChofer(id, azar), plantaInicial, reloj, observador));
    }
    return camiones;
  }

  private static Chofer crearChofer(int id, Random azar) {
    int horas = VIAJE_MINIMO_HORAS + azar.nextInt(VIAJE_MAXIMO_HORAS - VIAJE_MINIMO_HORAS + 1);
    return new Chofer("Chofer " + id, horas);
  }
}
