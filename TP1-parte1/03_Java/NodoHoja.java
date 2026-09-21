package procesos;

public class NodoHoja extends NodoProceso {

  private static final long PAUSA_VERIFICACION_MS = 15_000;
  private static final long MILISEGUNDOS_POR_SEGUNDO = 1_000;

  public NodoHoja(String nombre) {
    super(nombre);
  }

  @Override
  public void ejecutar() {
    identificarse();
    pausarParaVerificacion();
    informarFinalizacion();
  }

  private void pausarParaVerificacion() {
    long segundos = PAUSA_VERIFICACION_MS / MILISEGUNDOS_POR_SEGUNDO;
    System.out.println("Proceso " + nombre + " es una hoja del árbol. Se mantiene vivo "
        + segundos + " segundos para permitir la verificación.");
    dormir(PAUSA_VERIFICACION_MS);
  }

  private void dormir(long milisegundos) {
    try {
      Thread.sleep(milisegundos);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
    }
  }
}
