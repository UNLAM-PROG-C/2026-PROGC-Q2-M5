#include "reloj.h"

namespace bano
{

  Reloj::Reloj() : inicio_(std::chrono::steady_clock::now()) {}

  double Reloj::Milisegundos() const
  {
    const std::chrono::duration<double, std::milli> transcurrido = std::chrono::steady_clock::now() - inicio_;
    return transcurrido.count();
  }

}  // namespace bano
