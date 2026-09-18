package cargacriolla;

import static cargacriolla.Constantes.CARGA_HORAS;
import static cargacriolla.Constantes.COMBUSTIBLE_HORAS;
import static cargacriolla.Constantes.DESCARGA_HORAS;

import java.util.Optional;

/**
 * Un camion es un hilo. Sincroniza unicamente a traves de los recursos de las plantas (zonas y
 * surtidores) y de la cola de viajes pendientes; nunca retiene un recurso mientras espera otro,
 * asi que no puede haber deadlock.
 */
final class Camion implements Runnable {
  private final int id;
  private final Chofer chofer;
  private final Reloj reloj;
  private final ObservadorEstado observador;
  private Planta planta;
  private Optional<Viaje> carga = Optional.empty();

  Camion(int id, Chofer chofer, Planta plantaInicial, Reloj reloj, ObservadorEstado observador) {
    this.id = id;
    this.chofer = chofer;
    this.planta = plantaInicial;
    this.reloj = reloj;
    this.observador = observador;
  }

  @Override
  public void run() {
    boolean operando = true;
    while (operando) {
      descargarSiTraeCarga();
      operando = despacharDesdePlantaActual();
    }
    informar(EstadoCamion.FINALIZADO, "no quedan viajes por realizar");
  }

  int id() {
    return id;
  }

  private boolean despacharDesdePlantaActual() {
    if (cargarViaje().isPresent()) {
      repostarSiCorresponde();
      viajar();
      return true;
    }
    if (planta.destino().tieneViajesPendientes()) {
      viajar();
      return true;
    }
    return false;
  }

  private Optional<Viaje> cargarViaje() {
    informar(EstadoCamion.ESPERANDO_CARGA, "en " + planta.nombre());
    planta.zonaCarga().ocupar();
    try {
      carga = planta.tomarViaje();
      carga.ifPresent(this::cargar);
    } finally {
      planta.zonaCarga().liberar();
    }
    return carga;
  }

  private void cargar(Viaje viaje) {
    informar(EstadoCamion.CARGANDO, viaje.descripcion() + " en " + planta.nombre());
    reloj.esperarHoras(CARGA_HORAS);
  }

  private void repostarSiCorresponde() {
    planta.surtidores().ifPresent(this::repostar);
  }

  private void repostar(Recurso surtidores) {
    informar(EstadoCamion.ESPERANDO_COMBUSTIBLE, "en " + planta.nombre());
    surtidores.ocupar();
    try {
      informar(EstadoCamion.CARGANDO_COMBUSTIBLE, "surtidor Diesel asignado");
      reloj.esperarHoras(COMBUSTIBLE_HORAS);
    } finally {
      surtidores.liberar();
    }
  }

  private void viajar() {
    EstadoCamion estado =
        carga.isPresent() ? EstadoCamion.VIAJANDO_CARGADO : EstadoCamion.VIAJANDO_VACIO;
    informar(estado, "hacia " + planta.destino().nombre() + " (" + chofer.horasDeViaje() + " hs)");
    reloj.esperarHoras(chofer.horasDeViaje());
    planta = planta.destino();
  }

  private void descargarSiTraeCarga() {
    if (carga.isEmpty()) {
      return;
    }
    informar(EstadoCamion.ESPERANDO_DESCARGA, "en " + planta.nombre());
    planta.zonaDescarga().ocupar();
    try {
      descargar();
    } finally {
      planta.zonaDescarga().liberar();
    }
    informar(EstadoCamion.ENTREGADO, carga.get().descripcion() + " en " + planta.nombre());
    carga = Optional.empty();
  }

  private void descargar() {
    informar(EstadoCamion.DESCARGANDO, carga.get().descripcion() + " en " + planta.nombre());
    reloj.esperarHoras(DESCARGA_HORAS);
    reloj.registrarEntrega();
  }

  private void informar(EstadoCamion estado, String detalle) {
    observador.alCambiarEstado(new EventoCamion(reloj.horasSimuladas(), id, estado, detalle));
  }
}
