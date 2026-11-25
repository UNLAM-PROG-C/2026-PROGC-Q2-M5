// Pruebas de estres del bano compartido.
//
// Comprueba dos cosas:
// 1. El bano real nunca mezcla hombres y mujeres, nunca supera la capacidad y respeta el turno, aun con
//    muchos empleados y tiempos muy comprimidos (mucha mas contencion que la corrida normal).
// 2. El auditor de verdad detecta los errores: se le pasan dos politicas defectuosas a proposito (sin
//    control de sexo y sin limite de capacidad) y tiene que dar la alarma.

#include <algorithm>
#include <iostream>
#include <vector>

#include "../src/constantes.h"
#include "../src/observador.h"
#include "../src/politica_admision.h"
#include "../src/simulacion.h"

namespace
{

  constexpr double kEscalaRapida = 0.05;
  constexpr int kRepeticiones = 10;
  constexpr int kIntentosDeteccion = 10;

  struct Configuracion
  {
    int hombres;
    int mujeres;
  };

  const std::vector<Configuracion> kConfiguraciones = {{1, 0}, {0, 1}, {5, 5}, {8, 6}, {0, 40}, {40, 0}, {25, 25}, {60, 60}};

  // Defectuosa: deja entrar a cualquiera mientras haya lugar (hombres y mujeres se mezclan).
  class PoliticaSinControlDeSexo : public bano::IPoliticaAdmision
  {
   public:
    bool PuedeEntrar(const bano::EstadoBano& estado, int turno, bano::Sexo) const override
    {
      return turno == estado.turno_que_puede_entrar && estado.adentro < bano::kCapacidadBano;
    }
  };

  // Defectuosa: no cuenta cuantos hay adentro (se supera la capacidad).
  class PoliticaSinLimiteDeCapacidad : public bano::IPoliticaAdmision
  {
   public:
    bool PuedeEntrar(const bano::EstadoBano& estado, int turno, bano::Sexo sexo) const override
    {
      return turno == estado.turno_que_puede_entrar && (estado.adentro == 0 || estado.sexo_actual == sexo);
    }
  };

  bool VerificarConfiguracion(const Configuracion& configuracion, int& maximo_visto)
  {
    const bano::PoliticaFifoEstricta politica;
    bool todo_ok = true;
    for (int repeticion = 0; repeticion < kRepeticiones; ++repeticion)
    {
      const bano::InformeAuditoria informe = bano::Simular(configuracion.hombres, configuracion.mujeres, politica, {}, kEscalaRapida);
      maximo_visto = std::max(maximo_visto, informe.maximo_simultaneo);
      todo_ok = todo_ok && informe.EsCorrecto() && informe.TotalQueUsaron() == configuracion.hombres + configuracion.mujeres;
    }
    return todo_ok;
  }

  bool VerificarBanoReal()
  {
    bool todo_ok = true;
    int maximo_global = 0;
    for (const Configuracion& configuracion : kConfiguraciones)
    {
      int maximo = 0;
      const bool ok = VerificarConfiguracion(configuracion, maximo);
      maximo_global = std::max(maximo_global, maximo);
      todo_ok = todo_ok && ok;
      std::cout << "  " << configuracion.hombres << " hombres / " << configuracion.mujeres << " mujeres x" << kRepeticiones << ": " << (ok ? "OK" : "FALLA")
                << " (maximo adentro: " << maximo << ")\n";
    }
    const bool alcanzo_capacidad = maximo_global == bano::kCapacidadBano;
    std::cout << "  Se llego a la capacidad maxima (" << bano::kCapacidadBano << ") sin pasarse: " << (alcanzo_capacidad ? "si" : "NO") << "\n";
    return todo_ok && alcanzo_capacidad;
  }

  // True si, en algun intento, el auditor marca el error esperado con la politica defectuosa.
  template <typename Politica, typename Campo>
  bool ElAuditorDetecta(int hombres, int mujeres, Campo campo)
  {
    const Politica politica;
    for (int intento = 0; intento < kIntentosDeteccion; ++intento)
    {
      const bano::InformeAuditoria informe = bano::Simular(hombres, mujeres, politica, {}, kEscalaRapida);
      if (informe.*campo > 0)
      {
        return true;
      }
    }
    return false;
  }

  bool VerificarAuditor()
  {
    const bool detecta_mezclas = ElAuditorDetecta<PoliticaSinControlDeSexo>(20, 20, &bano::InformeAuditoria::mezclas);
    const bool detecta_excesos = ElAuditorDetecta<PoliticaSinLimiteDeCapacidad>(0, 60, &bano::InformeAuditoria::excesos_de_capacidad);
    std::cout << "  Politica sin control de sexo   -> el auditor detecta mezclas: " << (detecta_mezclas ? "si" : "NO") << "\n";
    std::cout << "  Politica sin limite de capacidad -> el auditor detecta excesos: " << (detecta_excesos ? "si" : "NO") << "\n";
    return detecta_mezclas && detecta_excesos;
  }

}  // namespace

int main()
{
  std::cout << "1) Bano real bajo estres\n";
  const bool bano_ok = VerificarBanoReal();
  std::cout << "2) El auditor detecta politicas defectuosas\n";
  const bool auditor_ok = VerificarAuditor();
  const bool todo_ok = bano_ok && auditor_ok;
  std::cout << "\nRESULTADO: " << (todo_ok ? "TODO OK" : "HAY FALLAS") << std::endl;
  return todo_ok ? 0 : bano::kCodigoError;
}
