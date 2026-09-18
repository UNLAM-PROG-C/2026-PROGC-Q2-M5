package cargacriolla;

import static cargacriolla.Constantes.CAPACIDAD_ZONA;

import java.util.Optional;
import java.util.Queue;

/**
 * Planta de carga y descarga. Admite como maximo dos camiones a la vez: uno en la zona de carga y
 * otro en la de descarga. Fernandez ademas tiene estacion de servicio con surtidores.
 */
final class Planta {
  private final String nombre;
  private final Queue<Viaje> viajesPendientes;
  private final Optional<Recurso> surtidores;
  private final Recurso zonaCarga = new Recurso(CAPACIDAD_ZONA);
  private final Recurso zonaDescarga = new Recurso(CAPACIDAD_ZONA);
  private Planta destino;

  Planta(String nombre, Queue<Viaje> viajesPendientes, Optional<Recurso> surtidores) {
    this.nombre = nombre;
    this.viajesPendientes = viajesPendientes;
    this.surtidores = surtidores;
  }

  /** Se llama una sola vez, antes de arrancar los hilos. */
  void enlazarCon(Planta otra) {
    destino = otra;
    otra.destino = this;
  }

  /** Reclama de forma atomica el proximo viaje pendiente, si quedan. */
  Optional<Viaje> tomarViaje() {
    return Optional.ofNullable(viajesPendientes.poll());
  }

  boolean tieneViajesPendientes() {
    return !viajesPendientes.isEmpty();
  }

  String nombre() {
    return nombre;
  }

  Planta destino() {
    return destino;
  }

  Recurso zonaCarga() {
    return zonaCarga;
  }

  Recurso zonaDescarga() {
    return zonaDescarga;
  }

  Optional<Recurso> surtidores() {
    return surtidores;
  }
}
