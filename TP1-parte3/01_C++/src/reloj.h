#ifndef RELOJ_H_
#define RELOJ_H_

#include <chrono>

namespace bano
{

  // Milisegundos transcurridos desde que arranco la simulacion.
  class Reloj
  {
   public:
    Reloj();

    double Milisegundos() const;

   private:
    std::chrono::steady_clock::time_point inicio_;
  };

}  // namespace bano

#endif  // RELOJ_H_
