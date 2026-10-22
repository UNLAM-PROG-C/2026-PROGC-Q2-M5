package cargacriolla;

import static cargacriolla.Constantes.HORAS_POR_DIA;
import static cargacriolla.Constantes.MINUTOS_POR_HORA;

/** Observer que imprime cada cambio de estado (una linea por evento, atomica entre hilos). */
final class RegistroConsola implements ObservadorEstado {
  static {
    // El primer String.format tarda decenas de ms (carga de clases) y falsearia el arranque.
    marcaDeTiempo(0);
  }

  @Override
  public void alCambiarEstado(EventoCamion evento) {
    System.out.println(formatear(evento));
  }

  private static String formatear(EventoCamion evento) {
    return String.format(
        "[%s] Camion %02d | %-24s | %s",
        marcaDeTiempo(evento.horasSimuladas()),
        evento.idCamion(),
        evento.estado().descripcion(),
        evento.detalle());
  }

  static String marcaDeTiempo(double horas) {
    int minutosPorDia = HORAS_POR_DIA * MINUTOS_POR_HORA;
    int totalMinutos = (int) Math.round(horas * MINUTOS_POR_HORA);
    int minutosDelDia = totalMinutos % minutosPorDia;
    return String.format(
        "Dia %d %02d:%02d",
        totalMinutos / minutosPorDia + 1,
        minutosDelDia / MINUTOS_POR_HORA,
        minutosDelDia % MINUTOS_POR_HORA);
  }
}
