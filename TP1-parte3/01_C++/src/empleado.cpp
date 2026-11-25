#include "empleado.h"

#include <thread>

namespace bano
{

  Empleado::Empleado(int id, Sexo sexo, Bano& bano, Milisegundos demora_llegada, Milisegundos duracion_uso)
      : id_(id), sexo_(sexo), bano_(bano), demora_llegada_(demora_llegada), duracion_uso_(duracion_uso)
  {
  }

  void Empleado::Usar()
  {
    std::this_thread::sleep_for(demora_llegada_);
    const int turno = bano_.Entrar(id_, sexo_);
    std::this_thread::sleep_for(duracion_uso_);
    bano_.Salir(id_, sexo_, turno);
  }

}  // namespace bano
