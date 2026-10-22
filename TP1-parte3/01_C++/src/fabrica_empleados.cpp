#include "fabrica_empleados.h"

#include <algorithm>

#include "constantes.h"

namespace bano
{
  namespace
  {

    std::unique_ptr<Empleado> CrearUno(int id, Sexo sexo, Bano& bano, std::mt19937& azar, double escala_tiempo)
    {
      std::uniform_int_distribution<int> llegada(0, kLlegadaMaximaMs);
      std::uniform_int_distribution<int> uso(kUsoMinimoMs, kUsoMaximoMs);
      const Milisegundos demora_llegada(llegada(azar) * escala_tiempo);
      const Milisegundos duracion_uso(uso(azar) * escala_tiempo);
      return std::make_unique<Empleado>(id, sexo, bano, demora_llegada, duracion_uso);
    }

  }  // namespace

  std::vector<std::unique_ptr<Empleado>> FabricaEmpleados::Crear(int hombres, int mujeres, Bano& bano, std::mt19937& azar, double escala_tiempo)
  {
    std::vector<Sexo> sexos(hombres, Sexo::kHombre);
    sexos.insert(sexos.end(), mujeres, Sexo::kMujer);
    std::shuffle(sexos.begin(), sexos.end(), azar);

    std::vector<std::unique_ptr<Empleado>> empleados;
    int id = 0;
    for (const Sexo sexo : sexos)
    {
      empleados.push_back(CrearUno(++id, sexo, bano, azar, escala_tiempo));
    }
    return empleados;
  }

}  // namespace bano
