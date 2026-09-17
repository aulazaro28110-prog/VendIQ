/* VendIQ · habla por correo con un cliente
   ------------------------------------------------------------------------
   Una bandeja de entrada con cuatro correos. Se abre uno, se pulsa Enviar, y
   la respuesta la escribe `componer_email()` (11_canales.py) con LA MISMA
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
    dia: 'Hoy',
    color: '#c43e1c',
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
    dia: 'Hoy',
    color: '#0f6cbd',
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
    dia: 'Hoy',
    color: '#0b6a0b',
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
    hora: '17:48',
    dia: 'Ayer',
    color: '#8764b8',
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

/* Las carpetas que existen pero no tienen nada dentro. Están porque un
   Outlook sin Borradores ni Eliminados no parece Outlook — pero no se
   quedan mudas al pulsarlas: cada una dice por qué está vacía. Fingir
   contenido ahí sería inventar datos. */
const VACIAS = {
  borradores: ['Sin borradores', 'Las respuestas se envían en cuanto las redacta el bot.'],
  eliminados: ['No hay nada eliminado', 'Los cuatro correos de ejemplo no se borran.'],
  archivo: ['El archivo está vacío', 'Esta bandeja se reinicia al recargar la página.'],
};

const iniciales = (nombre) => nombre.split(/\s+/).slice(0, 2)
  .map((p) => p[0] || '').join('').toUpperCase();

function contar() {
  $('#ol-n-entrada').textContent = BANDEJA.filter((c) => !c.leido).length || '';
  $('#ol-n-enviados').textContent = BANDEJA.filter((c) => c.respuesta).length || '';
}

/* --------------------------------------------------------------- la lista */
function pintarLista() {
  const lista = $('#ol-lista');
  lista.replaceChildren();

  if (VACIAS[CARPETA]) {
    const [titulo, pie] = VACIAS[CARPETA];
    const caja = crear('div', 'ol-vacia');
    caja.append(crear('b', null, titulo), crear('span', null, pie));
    lista.append(caja);
    return;
  }

  const visibles = CARPETA === 'entrada'
    ? BANDEJA : BANDEJA.filter((c) => c.respuesta);

  if (!visibles.length) {
    const caja = crear('div', 'ol-vacia');
    caja.append(crear('b', null, 'Nada enviado todavía'),
                crear('span', null, 'Abre un correo y pulsa Enviar.'));
    lista.append(caja);
    return;
  }

  // Agrupadas por día, como Outlook: Hoy, Ayer.
  let ultimoDia = null;
  visibles.forEach((c) => {
    if (c.dia !== ultimoDia) {
      ultimoDia = c.dia;
      const cab = crear('div', 'ol-dia');
      cab.append(crear('span', 'ol-chevron'), crear('span', null, c.dia));
      lista.append(cab);
    }

    const sobre = crear('button', 'ol-sobre');
    sobre.type = 'button';
    sobre.setAttribute('role', 'listitem');
    if (!c.leido) sobre.classList.add('sin-leer');
    if (ABIERTO === c.id) sobre.classList.add('abierto');

    const avatar = crear('div', 'ol-avatar', iniciales(c.de));
    avatar.style.background = c.color;

    const txt = crear('div', 'ol-sobre-txt');
    const fila = crear('div', 'ol-fila');
    fila.append(crear('span', 'ol-de', c.empresa || c.de),
                crear('span', 'ol-hora', c.hora));
    txt.append(fila,
               crear('p', 'ol-asunto', c.asunto),
               crear('p', 'ol-avance', c.cuerpo.split('\n')
                 .filter((l) => l.trim()).slice(1).join(' ')),
               crear('span', 'ol-que', c.que));

    sobre.append(avatar, txt);
    if (!c.leido) sobre.append(crear('span', 'ol-punto'));
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

  // La barra de acción, arriba y pegada, como el Enviar de Outlook.
  const barra = crear('div', 'ol-accion-barra');
  const bt = crear('button', 'ol-enviar');
  bt.type = 'button';
  bt.append(crear('span', 'ol-flecha', '➤'),
            crear('span', null, c.respuesta ? 'Volver a responder' : 'Responder'));
  bt.onclick = () => responder(c.id, bt);
  barra.append(bt);
  const de = crear('span', 'ol-cuenta-activa',
                   'De: alvaro@desguacesmadridnorte.com');
  barra.append(de);
  caja.append(barra);

  const cuerpo = crear('div', 'ol-lectura-cuerpo');
  const cab = crear('div', 'ol-cab');
  cab.append(crear('h4', null, c.asunto));
  const remite = crear('div', 'ol-remite');
  const avatar = crear('div', 'ol-avatar', iniciales(c.de));
  avatar.style.background = c.color;
  const datos = crear('div', 'ol-remite-datos');
  datos.append(crear('b', null, c.de + (c.empresa ? ' · ' + c.empresa : '')),
               crear('span', null, c.correo));
  remite.append(avatar, datos, crear('span', 'ol-hora', c.dia + ' ' + c.hora));
  cab.append(remite);
  cuerpo.append(cab, crear('p', 'ol-texto', c.cuerpo));

  if (c.respuesta) cuerpo.append(cajaRespuesta(c, c.respuesta));
  caja.append(cuerpo);
}

/* La respuesta, con la fila Para/CC/CCO y el sello de enviado: es lo que en
   Outlook distingue de un vistazo un mensaje que sale de uno que entra. */
function cajaRespuesta(c, d) {
  const caja = crear('div', 'ol-respuesta');

  const campos = crear('div', 'ol-campos');
  const para = crear('div', 'ol-campo');
  const chip = crear('span', 'ol-chip');
  chip.append(crear('span', null, c.de), crear('i', null, '✕'));
  para.append(crear('span', 'ol-campo-eti', 'Para'), chip);
  const cc = crear('span', 'ol-cc');
  cc.append(crear('span', null, 'CC'), crear('span', null, 'CCO'));
  para.append(cc);

  const asunto = crear('div', 'ol-campo');
  asunto.append(crear('span', 'ol-campo-eti', 'Asunto'),
                crear('span', null, d.asunto),
                crear('span', 'ol-sello', 'Enviado ' + horaAhora()));
  campos.append(para, asunto);

  const texto = crear('div', 'ol-respuesta-cuerpo');
  texto.append(crear('p', 'ol-texto', d.cuerpo));

  caja.append(campos, texto);
  return caja;
}

const horaAhora = () => new Date().toLocaleTimeString('es-ES',
  {hour: '2-digit', minute: '2-digit'});

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

  if (b.porque) carta.append(crear('p', 'nota', b.porque));

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
  bt.replaceChildren(crear('span', null, 'Redactando…'));
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
    pintarLectura();
    $('#ol-lectura').append(Object.assign(crear('p', 'ol-esperando'),
      {textContent: 'No se pudo redactar: ' + e.message}));
  }
}

/* ---------------------------------------------------------------- arranque */
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
