#ifndef FABRICA_EMPLEADOS_H_
#define FABRICA_EMPLEADOS_H_

#include <memory>
#include <random>
#include <vector>

#include "bano.h"
#include "empleado.h"

namespace bano
{

  // Factory Method: crea toda la plantilla en un solo hilo, antes de que arranque la simulacion.
  class FabricaEmpleados
  {
   public:
    static std::vector<std::unique_ptr<Empleado>> Crear(int hombres, int mujeres, Bano& bano, std::mt19937& azar, double escala_tiempo);
  };

}  // namespace bano

#endif  // FABRICA_EMPLEADOS_H_
