#ifndef OBSERVADOR_H_
#define OBSERVADOR_H_

#include <mutex>
#include <optional>

#include "evento.h"
#include "sexo.h"

namespace bano
{

  // Observer: recibe cada evento sin que el bano sepa que se hace con el.
  class IObservador
  {
   public:
    virtual ~IObservador() = default;
    virtual void AlRegistrarEvento(const EventoBano& evento) = 0;
  };

  // Imprime una linea por evento (el bano los emite de a uno por vez).
  class RegistroConsola : public IObservador
  {
   public:
    void AlRegistrarEvento(const EventoBano& evento) override;
  };

  // Lo que el auditor comprobo por su cuenta durante la simulacion.
  struct InformeAuditoria
  {
    int usaron_hombres = 0;
    int usaron_mujeres = 0;
    int maximo_simultaneo = 0;
    int mezclas = 0;
    int excesos_de_capacidad = 0;
    int fuera_de_turno = 0;

    int TotalQueUsaron() const;
    bool EsCorrecto() const;
  };

  // Recalcula el estado del bano solo a partir de los eventos, sin confiar en el bano.
  class Auditor : public IObservador
  {
   public:
    void AlRegistrarEvento(const EventoBano& evento) override;
    InformeAuditoria Informe() const;

   private:
    void RegistrarEntrada(const EventoBano& evento);
    void ContarAdentro();
    void RegistrarSalida(const EventoBano& evento);

    mutable std::mutex candado_;
    InformeAuditoria informe_;
    int adentro_ = 0;
    std::optional<Sexo> sexo_actual_;
    int proximo_turno_ = 0;
  };

}  // namespace bano

#endif  // OBSERVADOR_H_
