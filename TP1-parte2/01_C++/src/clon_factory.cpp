#include "clon_factory.h"

#include <random>

#include "constantes.h"

namespace naruto
{
  namespace
  {

    int GenerarChakraAleatorio(std::mt19937& generador)
    {
      std::uniform_int_distribution<int> distribucion(kChakraMinimo, kChakraMaximo);
      return distribucion(generador);
    }

  }  // namespace

  std::vector<ClonDeSombra> FabricaClones::CrearClones(int cantidad, const IEstrategiaIntento& estrategia)
  {
    std::mt19937 generador_semillas(std::random_device{}());
    std::vector<ClonDeSombra> clones;

    // reserve() es obligatorio: ClonDeSombra guarda una referencia y no
    // es move-asignable, así que el vector no puede reubicar elementos.
    clones.reserve(cantidad);

    for (int id = 0; id < cantidad; ++id)
    {
      const int chakra = GenerarChakraAleatorio(generador_semillas);
      const unsigned int semilla = generador_semillas();
      clones.emplace_back(id, chakra, semilla, estrategia);
    }
    return clones;
  }

}  // namespace naruto
