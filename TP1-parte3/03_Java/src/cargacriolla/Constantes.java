package cargacriolla;

/** Parametros del relevamiento operativo de Carga Criolla S.A. */
final class Constantes {
  static final int VIAJE_MINIMO_HORAS = 18;
  static final int VIAJE_MAXIMO_HORAS = 24;
  static final int CARGA_HORAS = 2;
  static final int DESCARGA_HORAS = 2;
  static final int COMBUSTIBLE_HORAS = 1;

  static final int CANTIDAD_PLANTAS = 2;
  static final int CAPACIDAD_ZONA = 1;
  static final int SURTIDORES_DIESEL = 2;

  static final int HORAS_POR_DIA = 24;
  static final int MINUTOS_POR_HORA = 60;
  static final long MS_REALES_POR_HORA_SIMULADA = 20;
  static final long MARGEN_ESPERA_ACTIVA_MS = 16;
  static final long NANOS_POR_MS = 1_000_000L;

  private Constantes() {}
}
