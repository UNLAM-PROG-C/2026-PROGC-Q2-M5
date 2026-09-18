#ifndef SIMULACION_H_
#define SIMULACION_H_

#include <vector>

#include "observador.h"
#include "politica_admision.h"

namespace bano
{

  // Arma el bano y la plantilla, lanza un hilo por empleado y espera con join().
  // Devuelve lo que comprobo el auditor. Los observadores extra (ej. el log) son opcionales.
  InformeAuditoria Simular(int hombres, int mujeres, const IPoliticaAdmision& politica, const std::vector<IObservador*>& observadores, double escala_tiempo);

}  // namespace bano

#endif  // SIMULACION_H_
