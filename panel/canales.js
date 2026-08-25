/* VendIQ · los tres canales
   ------------------------------------------------------------------------
   Pega un correo de cliente y sale la respuesta entera. La búsqueda que corre
   por debajo es LA MISMA que la del chat de WhatsApp, y el guardarraíl de
   precio también: lo único que cambia es la forma.

   Por eso al lado de la respuesta se enseña la consulta DESTILADA. Es la parte
   que no se ve y la que decide si el correo sale bien: un correo entero tiene
   ochenta palabras de cortesía que hunden la cobertura léxica, así que antes de
   buscar se le quita todo menos lo que nombra la pieza y el coche. */

const EJEMPLO_CORREO = {
  asunto: '¿Tenéis alternador de AUDI A4?',
  cuerpo: `Buenos días:

Les escribo desde Talleres Motor Sur (Getafe). Necesitamos un alternador para un AUDI A4 2.0 TFSI del año 2012.
Matrícula del vehículo: 4521 KBD.

¿Nos pueden confirmar disponibilidad, precio, plazo de entrega y garantía? Trabajamos con factura.

Un saludo,
Javier Ruiz
Talleres Motor Sur`,
  quien: 'Javier Ruiz',
  empresa: 'Talleres Motor Sur',
};

function pintarRespuestaCorreo(d) {
  const caja = $('#correo-salida');
  caja.replaceChildren();

  const cab = crear('div', 'correo-cab');
  cab.append(crear('span', 'pastilla p-gris', 'Asunto'),
             crear('strong', null, d.asunto));
  caja.append(cab);

  const cuerpo = crear('pre', 'correo-cuerpo');
  cuerpo.textContent = d.cuerpo;
  caja.append(cuerpo);

  // La traza. Cada párrafo con la regla que lo puso, igual que en el chat.
  const traza = crear('div', 'correo-traza');
  traza.append(crear('h4', null, 'Por qué dice eso'));
  const b = d.busqueda || {};
  const destilado = crear('p', 'nota');
  destilado.textContent = 'Consulta destilada: «' + (b.consulta_destilada || '') +
    '» · ' + (b.decision || '') + (b.identificado ? ' · coche identificado'
                                                  : ' · SIN identificar el coche');
  traza.append(destilado);
  (d.reglas || []).forEach(([regla, porque]) => {
    const fila = crear('div', 'regla');
    fila.append(crear('span', 'pastilla ' +
                      (regla.includes('NO autorizado') ? 'p-ambar' : 'p-ok'), regla));
    fila.append(crear('span', 'regla-porque', porque));
    traza.append(fila);
  });
  caja.append(traza);
}

async function responderCorreo() {
  const bt = $('#btn-correo');
  bt.disabled = true;
  try {
    const d = await api('/api/correo', {
      asunto: $('#correo-asunto').value.trim(),
      cuerpo: $('#correo-cuerpo').value.trim(),
      quien: $('#correo-quien').value.trim(),
      empresa: $('#correo-empresa').value.trim(),
    });
    pintarRespuestaCorreo(d);
  } catch (e) {
    $('#correo-salida').replaceChildren(Object.assign(
      crear('div', 'estado-vacio'), {textContent: 'No se pudo: ' + e.message}));
  } finally {
    bt.disabled = false;
  }
}

function ponerEjemplo() {
  $('#correo-asunto').value = EJEMPLO_CORREO.asunto;
  $('#correo-cuerpo').value = EJEMPLO_CORREO.cuerpo;
  $('#correo-quien').value = EJEMPLO_CORREO.quien;
  $('#correo-empresa').value = EJEMPLO_CORREO.empresa;
}

if ($('#btn-correo')) {
  $('#btn-correo').onclick = responderCorreo;
  $('#btn-correo-ejemplo').onclick = () => { ponerEjemplo(); responderCorreo(); };
  ponerEjemplo();
}
