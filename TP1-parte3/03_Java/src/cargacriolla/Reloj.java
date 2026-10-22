package cargacriolla;

import static cargacriolla.Constantes.MARGEN_ESPERA_ACTIVA_MS;
import static cargacriolla.Constantes.MS_REALES_POR_HORA_SIMULADA;
import static cargacriolla.Constantes.NANOS_POR_MS;

import java.util.concurrent.atomic.AtomicLong;

/**
 * Reloj de la simulacion: cada hora simulada dura unos pocos milisegundos reales. En Windows
 * Thread.sleep se pasa entre 8 y 15 ms por el timer del sistema, un error enorme frente a 20 ms por
 * hora simulada. Por eso se duerme casi todo el intervalo y se espera activamente el tramo final
 * hasta una hora limite exacta.
 */
final class Reloj {
  private final long inicioNanos = System.nanoTime();
  private final AtomicLong ultimaEntregaNanos = new AtomicLong();

  double horasSimuladas() {
    return horasDesdeInicio(System.nanoTime() - inicioNanos);
  }

  void esperarHoras(int horas) {
    long limiteNanos = System.nanoTime() + horas * MS_REALES_POR_HORA_SIMULADA * NANOS_POR_MS;
    dormirHastaCercaDe(limiteNanos);
    while (System.nanoTime() < limiteNanos) {
      Thread.onSpinWait();
    }
  }

  void registrarEntrega() {
    ultimaEntregaNanos.accumulateAndGet(System.nanoTime() - inicioNanos, Math::max);
  }

  double horasHastaUltimaEntrega() {
    return horasDesdeInicio(ultimaEntregaNanos.get());
  }

  private static void dormirHastaCercaDe(long limiteNanos) {
    long dormirMs = (limiteNanos - System.nanoTime()) / NANOS_POR_MS - MARGEN_ESPERA_ACTIVA_MS;
    if (dormirMs <= 0) {
      return;
    }
    try {
      Thread.sleep(dormirMs);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException("Simulacion interrumpida", e);
    }
  }

  private static double horasDesdeInicio(long nanos) {
    return (double) nanos / NANOS_POR_MS / MS_REALES_POR_HORA_SIMULADA;
  }
}
