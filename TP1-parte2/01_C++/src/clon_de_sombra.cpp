#include "clon_de_sombra.h"

#include <chrono>
#include <thread>

namespace naruto
{

  ClonDeSombra::ClonDeSombra(int id, int chakra_inicial, unsigned int semilla, const IEstrategiaIntento& estrategia)
      : id_(id), chakra_inicial_(chakra_inicial), generador_(semilla), estrategia_(estrategia)
  {
  }

  int ClonDeSombra::Entrenar()
  {
    int niveles_ganados = 0;
    for (int intento = 0; intento < chakra_inicial_; ++intento)
    {
      const ResultadoIntento resultado = estrategia_.Resolver(generador_);
      std::this_thread::sleep_for(std::chrono::milliseconds(resultado.duracion_ms));
      niveles_ganados += resultado.subio_nivel ? 1 : 0;
    }
    return niveles_ganados;
  }

  int ClonDeSombra::id() const { return id_; }

}  // namespace naruto
