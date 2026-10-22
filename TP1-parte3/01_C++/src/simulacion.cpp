#include "simulacion.h"

#include <memory>
#include <random>
#include <thread>

#include "bano.h"
#include "empleado.h"
#include "fabrica_empleados.h"
#include "reloj.h"

namespace bano
{
  namespace
  {

    void EjecutarHilos(const std::vector<std::unique_ptr<Empleado>>& empleados)
    {
      std::vector<std::thread> hilos;
      hilos.reserve(empleados.size());
      for (const std::unique_ptr<Empleado>& empleado : empleados)
      {
        hilos.emplace_back(&Empleado::Usar, empleado.get());
      }
      for (std::thread& hilo : hilos)
      {
        hilo.join();
      }
    }

  }  // namespace

  InformeAuditoria Simular(int hombres, int mujeres, const IPoliticaAdmision& politica, const std::vector<IObservador*>& observadores, double escala_tiempo)
  {
    Auditor auditor;
    std::vector<IObservador*> todos = observadores;
    todos.push_back(&auditor);

    const Reloj reloj;
    Bano bano(politica, todos, reloj);
    std::mt19937 azar{std::random_device{}()};
    EjecutarHilos(FabricaEmpleados::Crear(hombres, mujeres, bano, azar, escala_tiempo));
    return auditor.Informe();
  }

}  // namespace bano
