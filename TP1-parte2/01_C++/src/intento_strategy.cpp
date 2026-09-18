#include "intento_strategy.h"

#include "constantes.h"

namespace naruto
{

  ResultadoIntento EstrategiaIntentoProbabilistico::Resolver(std::mt19937& generador) const
  {
    std::uniform_int_distribution<int> distribucion_duracion(kDuracionIntentoMinimoMs, kDuracionIntentoMaximoMs);
    std::bernoulli_distribution distribucion_exito(kProbabilidadSubirNivel);

    const int duracion_ms = distribucion_duracion(generador);
    const bool subio_nivel = distribucion_exito(generador);

    return ResultadoIntento{duracion_ms, subio_nivel};
  }

}  // namespace naruto
