#ifndef CLON_FACTORY_H_
#define CLON_FACTORY_H_

#include <vector>

#include "clon_de_sombra.h"
#include "intento_strategy.h"

namespace naruto
{

  // Factory Method: crea la tanda de clones con su chakra y su semilla
  // asignados de forma secuencial (un solo hilo), antes de que arranque
  // el entrenamiento concurrente.
  class FabricaClones
  {
   public:
    static std::vector<ClonDeSombra> CrearClones(int cantidad, const IEstrategiaIntento& estrategia);
  };

}  // namespace naruto

#endif  // CLON_FACTORY_H_
