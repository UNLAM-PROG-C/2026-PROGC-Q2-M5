#include "politica_admision.h"

#include "constantes.h"

namespace bano
{

  bool PoliticaFifoEstricta::PuedeEntrar(const EstadoBano& estado, int turno, Sexo sexo) const
  {
    if (turno != estado.turno_que_puede_entrar)
    {
      return false;
    }
    const bool mismo_sexo = estado.sexo_actual == sexo;
    return estado.adentro == 0 || (mismo_sexo && estado.adentro < kCapacidadBano);
  }

}  // namespace bano
