package cargacriolla;

/** Cambio de estado de un camion, con el instante simulado en que ocurrio. */
record EventoCamion(double horasSimuladas, int idCamion, EstadoCamion estado, String detalle) {}
