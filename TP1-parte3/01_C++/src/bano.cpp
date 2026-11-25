#include "bano.h"

#include <utility>

namespace bano
{

  Bano::Bano(const IPoliticaAdmision& politica, std::vector<IObservador*> observadores, const Reloj& reloj)
      : politica_(politica), observadores_(std::move(observadores)), reloj_(reloj)
  {
  }

  int Bano::Entrar(int id_empleado, Sexo sexo)
  {
    std::unique_lock<std::mutex> lock(candado_);
    const int turno = TomarTurno(id_empleado, sexo);
    condicion_.wait(lock, [&] { return politica_.PuedeEntrar(estado_, turno, sexo); });
    Ingresar(id_empleado, sexo, turno);
    return turno;
  }

  void Bano::Salir(int id_empleado, Sexo sexo, int turno)
  {
    std::lock_guard<std::mutex> lock(candado_);
    --estado_.adentro;
    if (estado_.adentro == 0)
    {
      estado_.sexo_actual.reset();
    }
    Notificar(id_empleado, sexo, TipoEvento::kSale, turno);
    condicion_.notify_all();
  }

  int Bano::TomarTurno(int id_empleado, Sexo sexo)
  {
    const int turno = proximo_turno_a_entregar_++;
    Notificar(id_empleado, sexo, TipoEvento::kLlega, turno);
    return turno;
  }

  void Bano::Ingresar(int id_empleado, Sexo sexo, int turno)
  {
    estado_.sexo_actual = sexo;
    ++estado_.adentro;
    ++estado_.turno_que_puede_entrar;
    Notificar(id_empleado, sexo, TipoEvento::kEntra, turno);
    condicion_.notify_all();
  }

  void Bano::Notificar(int id_empleado, Sexo sexo, TipoEvento tipo, int turno)
  {
    const EventoBano evento{reloj_.Milisegundos(), id_empleado, sexo, tipo, turno, estado_.adentro};
    for (IObservador* observador : observadores_)
    {
      observador->AlRegistrarEvento(evento);
    }
  }

}  // namespace bano
