package cargacriolla;

/** Mercaderia que transporta la empresa. */
enum Carga {
  HARINA("bolsones de harina"),
  CARBON("bolsas de carbon");

  private final String descripcion;

  Carga(String descripcion) {
    this.descripcion = descripcion;
  }

  String descripcion() {
    return descripcion;
  }
}
