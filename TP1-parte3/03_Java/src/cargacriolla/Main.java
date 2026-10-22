package cargacriolla;

import java.util.Locale;

/** Uso: Main {@code <camiones> <viajes_por_planta> [--csv]}. */
public final class Main {
  private static final String USO = "Uso: Main <camiones> <viajes_por_planta> [--csv]";
  private static final String OPCION_CSV = "--csv";
  private static final int ARGUMENTOS_OBLIGATORIOS = 2;
  private static final int INDICE_CAMIONES = 0;
  private static final int INDICE_VIAJES = 1;
  private static final int CODIGO_ERROR_USO = 1;

  private Main() {}

  private record Argumentos(int camiones, int viajesPorPlanta, boolean csv) {
    static Argumentos leer(String[] args) {
      if (args.length < ARGUMENTOS_OBLIGATORIOS) {
        throw new IllegalArgumentException(USO);
      }
      int camiones = Integer.parseInt(args[INDICE_CAMIONES]);
      int viajes = Integer.parseInt(args[INDICE_VIAJES]);
      if (camiones < 1 || viajes < 0) {
        throw new IllegalArgumentException(USO + " (camiones >= 1, viajes >= 0)");
      }
      boolean csv =
          args.length > ARGUMENTOS_OBLIGATORIOS && OPCION_CSV.equals(args[ARGUMENTOS_OBLIGATORIOS]);
      return new Argumentos(camiones, viajes, csv);
    }
  }

  public static void main(String[] args) {
    try {
      Argumentos argumentos = Argumentos.leer(args);
      imprimir(ejecutar(argumentos), argumentos.csv());
    } catch (IllegalArgumentException error) {
      System.err.println(error.getMessage());
      System.exit(CODIGO_ERROR_USO);
    }
  }

  private static ResultadoSimulacion ejecutar(Argumentos argumentos) {
    ObservadorEstado observador = argumentos.csv() ? evento -> {} : new RegistroConsola();
    return new Simulacion(observador).ejecutar(argumentos.camiones(), argumentos.viajesPorPlanta());
  }

  private static void imprimir(ResultadoSimulacion resultado, boolean csv) {
    if (csv) {
      System.out.println(String.format(Locale.ROOT, "%d,%d,%.2f,%.4f", resultado.camiones(),
          resultado.viajesPorPlanta(), resultado.horas(), resultado.dias()));
      return;
    }
    System.out.println(String.format(Locale.ROOT,
        "%nSimulacion finalizada: %d camiones, %d viajes por planta (%d en total)%n"
            + "Tiempo requerido: %.2f dias (%.1f hs simuladas)",
        resultado.camiones(), resultado.viajesPorPlanta(), resultado.viajesTotales(),
        resultado.dias(), resultado.horas()));
  }
}
