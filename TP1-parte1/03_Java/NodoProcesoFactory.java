package procesos;

import java.util.List;

public final class NodoProcesoFactory {

  private NodoProcesoFactory() {

  }

  public static NodoProceso crear(String nombre) {
    List<String> hijos = ProcessTree.obtenerHijos(nombre);
    return hijos.isEmpty() ? new NodoHoja(nombre) : new NodoInterno(nombre, hijos);
  }
}
