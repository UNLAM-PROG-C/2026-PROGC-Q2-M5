package cargacriolla;

/** Estados por los que pasa un camion durante la simulacion. */
enum EstadoCamion {
  ESPERANDO_CARGA("espera zona de carga"),
  CARGANDO("cargando"),
  ESPERANDO_COMBUSTIBLE("espera surtidor"),
  CARGANDO_COMBUSTIBLE("cargando combustible"),
  VIAJANDO_CARGADO("parte cargado"),
  VIAJANDO_VACIO("parte vacio"),
  ESPERANDO_DESCARGA("espera zona de descarga"),
  DESCARGANDO("descargando"),
  ENTREGADO("entrego el viaje"),
  FINALIZADO("finaliza su turno");

  private final String descripcion;

  EstadoCamion(String descripcion) {
    this.descripcion = descripcion;
  }

  String descripcion() {
    return descripcion;
  }
}
