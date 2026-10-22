package cargacriolla;

/** Observer: recibe cada cambio de estado sin que el camion sepa que se hace con el. */
@FunctionalInterface
interface ObservadorEstado {
  void alCambiarEstado(EventoCamion evento);
}
