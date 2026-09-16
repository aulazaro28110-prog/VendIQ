/* VendIQ · habla por correo con un cliente
   ------------------------------------------------------------------------
   Una bandeja de entrada con cuatro correos. Se abre uno, se pulsa Responder,
   y la respuesta la escribe `componer_email()` (11_canales.py) con LA MISMA
   búsqueda y EL MISMO guardarraíl de precio que el chat de WhatsApp. Aquí no
   hay ni una respuesta guardada: todas se redactan en el momento contra el
   catálogo real.

   Los cuatro correos no son decorado. Cada uno está elegido para que falle o
   acierte por un motivo DISTINTO, que es lo que hay que poder enseñar:

     1. con matrícula y referencia OEM  -> el correo fácil, el que sale entero
     2. "lo he visto en vuestra web"    -> el que estaba roto hasta hoy
     3. con la dirección de la ficha    -> el atajo por número de stock
     4. una pieza que no llevamos       -> el "no" que aun así sirve de algo

   Debajo de la respuesta va SIEMPRE la traza: la consulta destilada, la
   decisión y la regla que puso cada párrafo. Sin eso esto es una demo bonita;
   con eso se puede defender que la respuesta sale de la búsqueda y no de un
   guion escrito a mano. No quitarla. */

const CORREOS = [
  {
    id: 'c1',
    de: 'Javier Ruiz',
    empresa: 'Talleres Motor Sur',
    correo: 'javier.ruiz@talleres.es',
    hora: '09:14',
    que: 'con matrícula y referencia',
    asunto: '¿Tenéis alternador de AUDI A4?',
    cuerpo: `Buenos días:

Necesitamos un alternador para un AUDI A4 2.0 TFSI del año 2012.
Matrícula del vehículo: 4521 KBD.

¿Nos pueden confirmar disponibilidad, precio, plazo de entrega y garantía? Trabajamos con factura.

Un saludo,
Javier Ruiz`,
  },
  {
    id: 'c2',
    de: 'Nuria Sanz',
    empresa: '',
    correo: 'nuria.sanz@talleres.es',
    hora: '10:02',
    que: 'lo vio en la web, sin código',
    asunto: 'Motor completo Toyota Camry',
    cuerpo: `Buenos días:

Hemos visto en su web que tienen disponible un motor completo para un Toyota Camry.

¿Sigue disponible? ¿Me pueden decir precio y plazo?

Un saludo,
Nuria Sanz`,
  },
  {
    id: 'c3',
    de: 'Fernando Gil',
    empresa: 'Mecánica Gil',
    correo: 'fernando.gil@mecanica.es',
    hora: '11:35',
    que: 'pega la ficha de la web',
    asunto: 'Consulta sobre una pieza de su web',
    cuerpo: `Buenas:

Estoy mirando esta pieza en su página:
https://desguacesmadridnorte.com/69933-pieza.html

¿Sigue estando disponible? ¿Cuánto tardaría en llegar?

Gracias,
Fernando Gil`,
  },
  {
    id: 'c4',
    de: 'Rocío Bravo',
    empresa: 'Auto Bravo',
    correo: 'rocio.bravo@auto.es',
    hora: '12:20',
    que: 'algo que no llevamos',
    asunto: 'Pastillas de freno Opel Corsa',
    cuerpo: `Buenos días:

Necesitaría un juego de pastillas de freno para un Opel Corsa 1.2 de 2016.
Matrícula: 4086 MMS.

¿Las tenéis? ¿Precio y plazo?

Un saludo,
Rocío Bravo`,
  },
];

/* Estado de la bandeja. `respuesta` se rellena cuando el bot contesta, y por
   eso vive aquí y no en el DOM: al volver a abrir un correo ya contestado se
   vuelve a ver su respuesta sin pedirla otra vez al servidor. */
const BANDEJA = CORREOS.map((c) => ({...c, leido: false, respuesta: null}));
let ABIERTO = null;
let CARPETA = 'entrada';

const iniciales = (nombre) => nombre.split(/\s+/).slice(0, 2)
  .map((p) => p[0] || '').join('').toUpperCase();

function contar() {
  const enviados = BANDEJA.filter((c) => c.respuesta).length;
  $('#ol-n-entrada').textContent = BANDEJA.filter((c) => !c.leido).length;
  $('#ol-n-enviados').textContent = enviados;
}

/* --------------------------------------------------------------- la lista */
function pintarLista() {
  const lista = $('#ol-lista');
  lista.replaceChildren();

  const visibles = CARPETA === 'entrada'
    ? BANDEJA : BANDEJA.filter((c) => c.respuesta);

  if (!visibles.length) {
    const vacio = crear('p', 'vacio', 'Todavía no has contestado ningún correo.');
    vacio.style.padding = '28px 16px';
    lista.append(vacio);
    return;
  }

  visibles.forEach((c) => {
    const sobre = crear('button', 'ol-sobre');
    sobre.type = 'button';
    sobre.setAttribute('role', 'listitem');
    if (!c.leido) sobre.classList.add('sin-leer');
    if (ABIERTO === c.id) sobre.classList.add('abierto');

    const fila = crear('div', 'ol-fila');
    fila.append(crear('span', 'ol-de', c.empresa || c.de),
                crear('span', 'ol-hora', c.hora));
    sobre.append(fila,
                 crear('p', 'ol-asunto', c.asunto),
                 crear('p', 'ol-avance', c.cuerpo.split('\n')
                   .filter((l) => l.trim()).slice(1).join(' ')),
                 crear('span', 'ol-que', c.que));
    sobre.onclick = () => abrir(c.id);
    lista.append(sobre);
  });
}

/* ------------------------------------------------------------- la lectura */
function pintarLectura() {
  const caja = $('#ol-lectura');
  caja.replaceChildren();
  const c = BANDEJA.find((x) => x.id === ABIERTO);
  if (!c) {
    caja.append(crear('p', 'vacio', 'Elige un correo de la lista.'));
    return;
  }

  const cab = crear('div', 'ol-cab');
  cab.append(crear('h4', null, c.asunto));
  const remite = crear('div', 'ol-remite');
  const datos = crear('div', 'ol-remite-datos');
  datos.append(crear('b', null, c.de + (c.empresa ? ' · ' + c.empresa : '')),
               crear('span', null, c.correo));
  remite.append(crear('div', 'ol-avatar', iniciales(c.de)), datos);
  cab.append(remite);
  caja.append(cab);

  caja.append(crear('p', 'ol-texto', c.cuerpo));

  const acciones = crear('div', 'ol-acciones');
  const bt = crear('button', 'ol-responder',
                   c.respuesta ? 'Volver a responder' : 'Responder');
  bt.type = 'button';
  bt.onclick = () => responder(c.id, bt);
  acciones.append(bt);
  caja.append(acciones);

  if (c.respuesta) caja.append(cajaRespuesta(c.respuesta));
}

function cajaRespuesta(d) {
  const caja = crear('div', 'ol-respuesta');
  caja.append(crear('p', 'ol-de-bot', 'VendIQ · respuesta automática'),
              crear('h5', null, d.asunto),
              crear('p', 'ol-texto', d.cuerpo));
  return caja;
}

/* ----------------------------------------------------------------- la traza
   Lo que hace defendible el apartado: la consulta que de verdad se le pasó al
   buscador, la decisión y la regla detrás de cada párrafo. */
function pintarTraza(d) {
  const caja = $('#correo-traza');
  caja.replaceChildren();
  if (!d) return;

  const carta = crear('div', 'carta');
  carta.append(crear('h3', null, 'Por qué dice eso'));

  const b = d.busqueda || {};
  const nota = crear('p', 'nota');
  nota.textContent = 'Consulta destilada: «' + (b.consulta_destilada || '')
    + '» · ' + (b.decision || '')
    + (b.identificado ? ' · coche identificado' : ' · SIN identificar el coche');
  carta.append(nota);

  const porque = crear('p', 'nota');
  porque.textContent = b.porque || '';
  carta.append(porque);

  (d.reglas || []).forEach(([regla, explica]) => {
    const fila = crear('div', 'regla');
    fila.append(crear('span', 'pastilla ' +
                      (regla.includes('NO autorizado') ? 'p-ambar' : 'p-ok'), regla),
                crear('span', 'regla-porque', explica));
    carta.append(fila);
  });

  caja.append(carta);
}

/* ------------------------------------------------------------------ acción */
function abrir(id) {
  ABIERTO = id;
  const c = BANDEJA.find((x) => x.id === id);
  if (c) c.leido = true;
  contar();
  pintarLista();
  pintarLectura();
  pintarTraza(c && c.respuesta ? c.respuesta : null);
}

async function responder(id, bt) {
  const c = BANDEJA.find((x) => x.id === id);
  if (!c) return;
  bt.disabled = true;
  bt.textContent = 'Redactando…';
  try {
    const d = await api('/api/correo', {
      asunto: c.asunto, cuerpo: c.cuerpo, quien: c.de, empresa: c.empresa,
    });
    c.respuesta = d;
    contar();
    pintarLista();
    pintarLectura();
    pintarTraza(d);
  } catch (e) {
    bt.disabled = false;
    bt.textContent = 'Responder';
    const aviso = crear('p', 'ol-esperando', 'No se pudo redactar: ' + e.message);
    $('#ol-lectura').append(aviso);
  }
}

/* ------------------------------------------------------------------ arranque */
if ($('#outlook')) {
  $$('.ol-carpeta').forEach((bt) => {
    bt.onclick = () => {
      CARPETA = bt.dataset.carpeta;
      $$('.ol-carpeta').forEach((o) => o.classList.toggle('activa', o === bt));
      pintarLista();
    };
  });
  contar();
  pintarLista();
  pintarLectura();
}
