package procesos;

public abstract class NodoProceso {

  private static final String PID_PADRE_DESCONOCIDO = "N/A";

  protected final String nombre;
  protected final long pid;

  protected NodoProceso(String nombre) {
    this.nombre = nombre;
    this.pid = ProcessHandle.current().pid();
  }

  public abstract void ejecutar();

  protected void identificarse() {
    System.out.println("Soy el proceso " + nombre + ". PID: " + pid
        + " | PID del padre: " + obtenerPidPadre());
  }

  protected void informarFinalizacion() {
    System.out.println("Proceso " + nombre + " (PID: " + pid + ") finalizado.");
  }

  private String obtenerPidPadre() {
    return ProcessHandle.current()
        .parent()
        .map(padre -> String.valueOf(padre.pid()))
        .orElse(PID_PADRE_DESCONOCIDO);
  }
}
