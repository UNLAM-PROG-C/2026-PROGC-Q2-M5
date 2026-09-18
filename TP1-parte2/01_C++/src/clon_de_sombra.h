#ifndef CLON_DE_SOMBRA_H_
#define CLON_DE_SOMBRA_H_

#include <random>

#include "intento_strategy.h"

namespace naruto
{

  // Representa un clon de sombra entrenando en su propio hilo.
  // Cada instancia tiene su propio generador aleatorio: nunca comparte
  // estado mutable con otro clon, por lo que no necesita sincronización.
  class ClonDeSombra
  {
   public:
    ClonDeSombra(int id, int chakra_inicial, unsigned int semilla, const IEstrategiaIntento& estrategia);

    int Entrenar();
    int id() const;

   private:
    int id_;
    int chakra_inicial_;
    std::mt19937 generador_;
    const IEstrategiaIntento& estrategia_;
  };

}  // namespace naruto

#endif  // CLON_DE_SOMBRA_H_
