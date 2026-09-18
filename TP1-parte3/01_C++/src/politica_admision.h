#ifndef POLITICA_ADMISION_H_
#define POLITICA_ADMISION_H_

#include <optional>

#include "sexo.h"

namespace bano
{

  // Lo que la politica necesita saber del bano para decidir.
  struct EstadoBano
  {
    int adentro = 0;
    std::optional<Sexo> sexo_actual;
    int turno_que_puede_entrar = 0;
  };

  // Strategy: decide si un empleado puede entrar ahora, desacoplado del monitor.
  class IPoliticaAdmision
  {
   public:
    virtual ~IPoliticaAdmision() = default;
    virtual bool PuedeEntrar(const EstadoBano& estado, int turno, Sexo sexo) const = 0;
  };

  // FIFO estricta: entra solo si es su turno y el bano esta vacio, o lo ocupa su mismo sexo y hay lugar.
  class PoliticaFifoEstricta : public IPoliticaAdmision
  {
   public:
    bool PuedeEntrar(const EstadoBano& estado, int turno, Sexo sexo) const override;
  };

}  // namespace bano

#endif  // POLITICA_ADMISION_H_
