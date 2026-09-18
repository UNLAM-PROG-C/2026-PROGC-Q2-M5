#ifndef BANO_H_
#define BANO_H_

#include <condition_variable>
#include <mutex>
#include <vector>

#include "evento.h"
#include "observador.h"
#include "politica_admision.h"
#include "reloj.h"
#include "sexo.h"

namespace bano
{

  // Monitor (mutex + condition_variable) con admision FIFO por numero de turno.
  //
  // Cada empleado toma un turno al llegar y solo entra cuando la politica lo autoriza. Con la politica
  // FIFO estricta, un empleado del otro sexo al frente de la fila frena a los de atras hasta que el
  // bano se vacia: nadie espera indefinidamente (no hay inanicion). El turno lo garantiza el diseno
  // porque ni los mutex ni los semaforos de C++ prometen orden de espera.
  class Bano
  {
   public:
    Bano(const IPoliticaAdmision& politica, std::vector<IObservador*> observadores, const Reloj& reloj);

    // Bloquea hasta poder entrar. Devuelve el turno que le toco.
    int Entrar(int id_empleado, Sexo sexo);
    void Salir(int id_empleado, Sexo sexo, int turno);

   private:
    int TomarTurno(int id_empleado, Sexo sexo);
    void Ingresar(int id_empleado, Sexo sexo, int turno);
    void Notificar(int id_empleado, Sexo sexo, TipoEvento tipo, int turno);

    const IPoliticaAdmision& politica_;
    std::vector<IObservador*> observadores_;
    const Reloj& reloj_;
    std::mutex candado_;
    std::condition_variable condicion_;
    EstadoBano estado_;
    int proximo_turno_a_entregar_ = 0;
  };

}  // namespace bano

#endif  // BANO_H_
