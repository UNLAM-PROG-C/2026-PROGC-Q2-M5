package cargacriolla;

import static cargacriolla.Constantes.SURTIDORES_DIESEL;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Queue;
import java.util.Random;
import java.util.concurrent.ConcurrentLinkedQueue;

/** Arma las dos plantas, lanza un hilo por camion y espera a que terminen todos con join(). */
final class Simulacion {
  private final ObservadorEstado observador;

  Simulacion(ObservadorEstado observador) {
    this.observador = observador;
  }

  ResultadoSimulacion ejecutar(int camiones, int viajesPorPlanta) {
    Planta tapiales = crearPlanta("Tapiales", Carga.HARINA, viajesPorPlanta, Optional.empty());
    Recurso surtidores = new Recurso(SURTIDORES_DIESEL);
    Planta fernandez =
        crearPlanta("Fernandez", Carga.CARBON, viajesPorPlanta, Optional.of(surtidores));
    tapiales.enlazarCon(fernandez);

    Reloj reloj = new Reloj();
    List<Camion> flota = FabricaCamiones.crear(camiones, tapiales, reloj, observador, new Random());
    esperar(lanzar(flota));
    return new ResultadoSimulacion(camiones, viajesPorPlanta, reloj.horasHastaUltimaEntrega());
  }

  private static Planta crearPlanta(
      String nombre, Carga carga, int viajes, Optional<Recurso> surtidores) {
    Queue<Viaje> pendientes = new ConcurrentLinkedQueue<>();
    for (int numero = 1; numero <= viajes; numero++) {
      pendientes.add(new Viaje(numero, carga));
    }
    return new Planta(nombre, pendientes, surtidores);
  }

  private static List<Thread> lanzar(List<Camion> flota) {
    List<Thread> hilos = new ArrayList<>();
    for (Camion camion : flota) {
      Thread hilo = new Thread(camion, "camion-" + camion.id());
      hilos.add(hilo);
      hilo.start();
    }
    return hilos;
  }

  private static void esperar(List<Thread> hilos) {
    for (Thread hilo : hilos) {
      try {
        hilo.join();
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Simulacion interrumpida", e);
      }
    }
  }
}
