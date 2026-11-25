#ifndef EVENTO_H_
#define EVENTO_H_

#include "sexo.h"

namespace bano
{

  enum class TipoEvento
  {
    kLlega,
    kEntra,
    kSale
  };

  // Algo que le paso a un empleado, con el instante en que ocurrio.
  struct EventoBano
  {
    double milisegundos;
    int id_empleado;
    Sexo sexo;
    TipoEvento tipo;
    int turno;
    int adentro;
  };

}  // namespace bano

#endif  // EVENTO_H_
