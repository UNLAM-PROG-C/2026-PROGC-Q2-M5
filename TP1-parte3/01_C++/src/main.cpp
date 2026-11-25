#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>

#include "constantes.h"
#include "observador.h"
#include "politica_admision.h"
#include "simulacion.h"

namespace
{

  const std::string kUso = "Uso: bano <hombres> <mujeres>";
  constexpr int kArgumentosEsperados = 3;

  std::pair<int, int> LeerArgumentos(int argc, char* argv[])
  {
    if (argc != kArgumentosEsperados)
    {
      throw std::invalid_argument(kUso);
    }
    const int hombres = std::stoi(argv[1]);
    const int mujeres = std::stoi(argv[2]);
    if (hombres < 0 || mujeres < 0 || hombres + mujeres == 0)
    {
      throw std::invalid_argument(kUso + " (cantidades >= 0, al menos un empleado)");
    }
    return {hombres, mujeres};
  }

  void ImprimirInforme(const bano::InformeAuditoria& informe, int total)
  {
    std::cout << "\nUsaron el bano " << informe.TotalQueUsaron() << " de " << total << " empleados (" << informe.usaron_hombres << " hombres, "
              << informe.usaron_mujeres << " mujeres)\n";
    std::cout << "Maximo simultaneo dentro del bano: " << informe.maximo_simultaneo << " (limite " << bano::kCapacidadBano << ")\n";
    std::cout << "Mezclas hombres/mujeres: " << informe.mezclas << "\n";
    std::cout << "Excesos de capacidad (mas de " << bano::kCapacidadBano << "): " << informe.excesos_de_capacidad << "\n";
    std::cout << "Ingresos fuera de turno: " << informe.fuera_de_turno << std::endl;
  }

}  // namespace

int main(int argc, char* argv[])
{
  try
  {
    const std::pair<int, int> cantidades = LeerArgumentos(argc, argv);
    const bano::PoliticaFifoEstricta politica;
    bano::RegistroConsola consola;
    const bano::InformeAuditoria informe = bano::Simular(cantidades.first, cantidades.second, politica, {&consola}, bano::kEscalaTiempoNormal);
    ImprimirInforme(informe, cantidades.first + cantidades.second);
    return informe.EsCorrecto() && informe.TotalQueUsaron() == cantidades.first + cantidades.second ? 0 : bano::kCodigoError;
  }
  catch (const std::exception& excepcion)
  {
    std::cerr << excepcion.what() << std::endl;
    return bano::kCodigoError;
  }
}
