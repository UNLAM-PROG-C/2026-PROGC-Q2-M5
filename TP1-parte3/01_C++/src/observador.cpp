#include "observador.h"

#include <algorithm>
#include <cstdio>
#include <iostream>
#include <string>

#include "constantes.h"

namespace bano
{
  namespace
  {

    std::string Descripcion(const EventoBano& evento)
    {
      switch (evento.tipo)
      {
        case TipoEvento::kLlega:
          return "llega y toma el turno " + std::to_string(evento.turno);
        case TipoEvento::kEntra:
          return "entra al bano (adentro: " + std::to_string(evento.adentro) + ", " + Plural(evento.sexo) + ")";
        case TipoEvento::kSale:
          return "sale del bano (adentro: " + std::to_string(evento.adentro) + ")";
      }
      return "";
    }

  }  // namespace

  void RegistroConsola::AlRegistrarEvento(const EventoBano& evento)
  {
    char linea[kTamanoLineaLog];
    std::snprintf(linea, sizeof(linea), "[%7.0f ms] Empleado %02d (%s) | %s", evento.milisegundos, evento.id_empleado, Simbolo(evento.sexo), Descripcion(evento).c_str());
    std::cout << linea << std::endl;
  }

  int InformeAuditoria::TotalQueUsaron() const
  {
    return usaron_hombres + usaron_mujeres;
  }

  bool InformeAuditoria::EsCorrecto() const
  {
    return mezclas == 0 && excesos_de_capacidad == 0 && fuera_de_turno == 0;
  }

  void Auditor::AlRegistrarEvento(const EventoBano& evento)
  {
    std::lock_guard<std::mutex> lock(candado_);
    if (evento.tipo == TipoEvento::kEntra)
    {
      RegistrarEntrada(evento);
    }
    else if (evento.tipo == TipoEvento::kSale)
    {
      RegistrarSalida(evento);
    }
  }

  InformeAuditoria Auditor::Informe() const
  {
    std::lock_guard<std::mutex> lock(candado_);
    return informe_;
  }

  void Auditor::RegistrarEntrada(const EventoBano& evento)
  {
    if (adentro_ > 0 && sexo_actual_ != evento.sexo)
    {
      ++informe_.mezclas;
    }
    if (evento.turno != proximo_turno_)
    {
      ++informe_.fuera_de_turno;
    }
    proximo_turno_ = evento.turno + 1;
    sexo_actual_ = evento.sexo;
    ContarAdentro();
  }

  void Auditor::ContarAdentro()
  {
    ++adentro_;
    informe_.maximo_simultaneo = std::max(informe_.maximo_simultaneo, adentro_);
    if (adentro_ > kCapacidadBano)
    {
      ++informe_.excesos_de_capacidad;
    }
  }

  void Auditor::RegistrarSalida(const EventoBano& evento)
  {
    --adentro_;
    (evento.sexo == Sexo::kHombre ? informe_.usaron_hombres : informe_.usaron_mujeres) += 1;
    if (adentro_ == 0)
    {
      sexo_actual_.reset();
    }
  }

}  // namespace bano
