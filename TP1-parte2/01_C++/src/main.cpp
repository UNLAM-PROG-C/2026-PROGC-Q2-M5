#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

#include "intento_strategy.h"
#include "simulador.h"

namespace
{

  const std::string kRutaResultadosCsv = "resultados/resultados.csv";

  void ImprimirResultado(const naruto::ResultadoSimulacion& resultado)
  {
    std::cout << "Clones: " << resultado.cantidad_clones << " | Tiempo: " << resultado.duracion_total_ms << " ms | Nivel total: " << resultado.nivel_total_alcanzado << std::endl;
  }

  void GuardarResultadoEnCsv(const naruto::ResultadoSimulacion& resultado, const std::string& ruta)
  {
    const bool archivo_existia = std::ifstream(ruta).good();
    std::ofstream archivo(ruta, std::ios::app);
    if (!archivo_existia)
    {
      archivo << "cantidad_clones,duracion_total_ms,nivel_total_alcanzado\n";
    }
    archivo << resultado.cantidad_clones << "," << resultado.duracion_total_ms << "," << resultado.nivel_total_alcanzado << "\n";
  }

  int LeerCantidadClones(int argc, char* argv[])
  {
    if (argc != 2)
    {
      throw std::invalid_argument("Uso: naruto_entrenamiento <cantidad_de_clones>");
    }
    return std::stoi(argv[1]);
  }

}  // namespace

int main(int argc, char* argv[])
{
  try
  {
    const int cantidad_clones = LeerCantidadClones(argc, argv);
    const naruto::EstrategiaIntentoProbabilistico estrategia;
    const naruto::Simulador simulador(estrategia);

    const naruto::ResultadoSimulacion resultado = simulador.Ejecutar(cantidad_clones);
    ImprimirResultado(resultado);
    GuardarResultadoEnCsv(resultado, kRutaResultadosCsv);
  }
  catch (const std::exception& excepcion)
  {
    std::cerr << excepcion.what() << std::endl;
    return 1;
  }
  return 0;
}
