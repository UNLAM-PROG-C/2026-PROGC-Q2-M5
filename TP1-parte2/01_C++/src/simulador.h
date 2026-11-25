#ifndef SIMULADOR_H_
#define SIMULADOR_H_

#include <cstdint>

#include "intento_strategy.h"

namespace naruto
{

  struct ResultadoSimulacion
  {
    int cantidad_clones;
    int64_t duracion_total_ms;
    int nivel_total_alcanzado;
  };

  class Simulador
  {
   public:
    explicit Simulador(const IEstrategiaIntento& estrategia);
    ResultadoSimulacion Ejecutar(int cantidad_clones) const;

   private:
    const IEstrategiaIntento& estrategia_;
  };

}  // namespace naruto

#endif  // SIMULADOR_H_
