package procesos;

import java.util.List;
import java.util.Map;

public final class ProcessTree {

  private static final Map<String, List<String>> ARBOL = Map.of(
      "A", List.of("B"),
      "B", List.of("C", "D"),
      "C", List.of("E"),
      "D", List.of("F", "G"),
      "E", List.of("H", "I"),
      "F", List.of(),
      "G", List.of(),
      "H", List.of(),
      "I", List.of());

  private ProcessTree() {
  }

  public static List<String> obtenerHijos(String nombreProceso) {
    return ARBOL.getOrDefault(nombreProceso, List.of());
  }
}
