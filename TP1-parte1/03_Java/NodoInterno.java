package procesos;

import java.io.File;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;


public class NodoInterno extends NodoProceso {

  private final List<String> nombresHijos;

  public NodoInterno(String nombre, List<String> nombresHijos) {
    super(nombre);
    this.nombresHijos = nombresHijos;
  }

  @Override
  public void ejecutar() {
    identificarse();
    Map<String, Process> hijos = crearHijosDeManeraConcurrente();
    esperarFinalizacionDeHijos(hijos);
    informarFinalizacion();
  }

  private Map<String, Process> crearHijosDeManeraConcurrente() {
    Map<String, Process> hijosCreados = new LinkedHashMap<>();
    for (String nombreHijo : nombresHijos) {
      intentarIniciarProceso(nombreHijo, hijosCreados);
    }
    return hijosCreados;
  }

  private void intentarIniciarProceso(String nombreHijo, Map<String, Process> hijosCreados) {
    try {
      hijosCreados.put(nombreHijo, construirProcessBuilder(nombreHijo).start());
    } catch (IOException e) {
      System.err.println("Error al crear el proceso " + nombreHijo + ": " + e.getMessage());
    }
  }

  private ProcessBuilder construirProcessBuilder(String nombreHijo) {
    String ejecutableJava = obtenerRutaEjecutableJava();
    String classpath = System.getProperty("java.class.path");
    ProcessBuilder constructor = new ProcessBuilder(
        ejecutableJava, "-cp", classpath, NodeProcess.class.getName(), nombreHijo);
    constructor.inheritIO();
    return constructor;
  }

  private String obtenerRutaEjecutableJava() {
    return System.getProperty("java.home") + File.separator + "bin" + File.separator + "java";
  }

  private void esperarFinalizacionDeHijos(Map<String, Process> hijos) {
    for (Map.Entry<String, Process> entrada : hijos.entrySet()) {
      esperarFinalizacionDeUnHijo(entrada.getKey(), entrada.getValue());
    }
  }

  private void esperarFinalizacionDeUnHijo(String nombreHijo, Process proceso) {
    try {
      int codigoSalida = proceso.waitFor();
      System.out.println("Proceso " + nombre + ": el hijo " + nombreHijo
          + " finalizó con código " + codigoSalida);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
    }
  }
}
