package procesos;

public final class NodeProcess {

  private static final int CANTIDAD_ARGUMENTOS_REQUERIDOS = 1;
  private static final int CODIGO_SALIDA_USO_INCORRECTO = 1;

  private NodeProcess() {
  }

  public static void main(String[] args) {
    if (args.length < CANTIDAD_ARGUMENTOS_REQUERIDOS) {
      mostrarUso();
      System.exit(CODIGO_SALIDA_USO_INCORRECTO);
      return;
    }

    NodoProceso nodo = NodoProcesoFactory.crear(args[0]);
    nodo.ejecutar();
  }

  private static void mostrarUso() {
    System.err.println("Uso: java procesos.NodeProcess <nombreDelProceso>");
  }
}
