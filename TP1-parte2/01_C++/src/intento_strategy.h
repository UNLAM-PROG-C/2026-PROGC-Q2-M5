#ifndef INTENTO_STRATEGY_H_
#define INTENTO_STRATEGY_H_

#include <random>

namespace naruto
{

  struct ResultadoIntento
  {
    int duracion_ms;
    bool subio_nivel;
  };

  // Strategy: encapsula cómo se resuelve un intento de entrenamiento,
  // desacoplado de ClonDeSombra para poder cambiar la probabilidad o
  // el modelo de duración sin tocar la clase del clon.
  class IEstrategiaIntento
  {
   public:
    virtual ~IEstrategiaIntento() = default;
    virtual ResultadoIntento Resolver(std::mt19937& generador) const = 0;
  };

  class EstrategiaIntentoProbabilistico : public IEstrategiaIntento
  {
   public:
    ResultadoIntento Resolver(std::mt19937& generador) const override;
  };

}  // namespace naruto

#endif  // INTENTO_STRATEGY_H_
