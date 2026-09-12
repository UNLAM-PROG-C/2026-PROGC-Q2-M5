#include "simulador.h"

#include <chrono>
#include <thread>
#include <vector>

#include "clon_de_sombra.h"
#include "clon_factory.h"

namespace naruto
{
  namespace
  {

    using RelojAlta = std::chrono::high_resolution_clock;

    // Lanza un hilo por clon. Cada hilo escribe únicamente en su propia
    // posición i de "niveles" (ya dimensionado), así que no hace falta
    // ningún mecanismo de sincronización entre ellos.
    std::vector<std::thread> LanzarHilos(std::vector<ClonDeSombra>& clones, std::vector<int>& niveles)
    {
      std::vector<std::thread> hilos;
      hilos.reserve(clones.size());
      for (size_t i = 0; i < clones.size(); ++i)
      {
        hilos.emplace_back([&clones, &niveles, i]() { niveles[i] = clones[i].Entrenar(); });
      }
      return hilos;
    }

    int SumarNiveles(const std::vector<int>& niveles)
    {
      int total = 0;
      for (const int nivel : niveles)
      {
        total += nivel;
      }
      return total;
    }

  }  // namespace

  Simulador::Simulador(const IEstrategiaIntento& estrategia) : estrategia_(estrategia) {}

  ResultadoSimulacion Simulador::Ejecutar(int cantidad_clones) const
  {
    std::vector<ClonDeSombra> clones = FabricaClones::CrearClones(cantidad_clones, estrategia_);
    std::vector<int> niveles_por_clon(cantidad_clones, 0);

    const RelojAlta::time_point inicio = RelojAlta::now();
    std::vector<std::thread> hilos = LanzarHilos(clones, niveles_por_clon);
    for (std::thread& hilo : hilos)
    {
      hilo.join();
    }
    const RelojAlta::time_point fin = RelojAlta::now();

    const auto duracion_ms = std::chrono::duration_cast<std::chrono::milliseconds>(fin - inicio).count();
    return ResultadoSimulacion{cantidad_clones, duracion_ms, SumarNiveles(niveles_por_clon)};
  }

}  // namespace naruto
