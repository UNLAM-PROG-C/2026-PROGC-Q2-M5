#ifndef SEXO_H_
#define SEXO_H_

namespace bano
{

  enum class Sexo
  {
    kHombre,
    kMujer
  };

  inline const char* Simbolo(Sexo sexo)
  {
    return sexo == Sexo::kHombre ? "H" : "M";
  }

  inline const char* Plural(Sexo sexo)
  {
    return sexo == Sexo::kHombre ? "hombres" : "mujeres";
  }

}  // namespace bano

#endif  // SEXO_H_
