#ifndef EMPLEADO_H_
#define EMPLEADO_H_

#include <chrono>

#include "bano.h"
#include "sexo.h"

namespace bano
{

  using Milisegundos = std::chrono::duration<double, std::milli>;

  // Un empleado: llega, espera su turno, usa el bano y sale. Su cuerpo (Usar) corre en un hilo propio
  // y solo se sincroniza a traves del bano.
  class Empleado
  {
   public:
    Empleado(int id, Sexo sexo, Bano& bano, Milisegundos demora_llegada, Milisegundos duracion_uso);

    void Usar();

   private:
    int id_;
    Sexo sexo_;
    Bano& bano_;
    Milisegundos demora_llegada_;
    Milisegundos duracion_uso_;
  };

}  // namespace bano

#endif  // EMPLEADO_H_
