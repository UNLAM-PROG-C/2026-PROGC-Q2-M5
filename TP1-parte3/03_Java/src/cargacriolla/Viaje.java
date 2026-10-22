package cargacriolla;

/** Solicitud de viaje: una carga que hay que llevar de una planta a la otra. */
record Viaje(int numero, Carga carga) {
  String descripcion() {
    return "viaje " + numero + " (" + carga.descripcion() + ")";
  }
}
