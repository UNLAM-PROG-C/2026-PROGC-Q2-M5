package cargacriolla;

import java.util.concurrent.Semaphore;

/**
 * Recurso compartido de capacidad limitada (zona de carga, de descarga o surtidores). El semaforo
 * es justo (FIFO): entra primero el camion que llego primero.
 */
final class Recurso {
  private final Semaphore semaforo;

  Recurso(int capacidad) {
    semaforo = new Semaphore(capacidad, true);
  }

  void ocupar() {
    try {
      semaforo.acquire();
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException("Simulacion interrumpida", e);
    }
  }

  void liberar() {
    semaforo.release();
  }
}
