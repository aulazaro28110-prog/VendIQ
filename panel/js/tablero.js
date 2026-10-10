/* VendIQ · la mesa de trabajo de las ofertas
   ========================================================================
   PASO 3. Un tablero por estado para GESTIONAR ofertas, no una lista pasiva:
   cada oferta es una tarjeta, al pulsarla se abre un panel lateral con su
   detalle, su histórico y un compositor con la respuesta sugerida.

   QUÉ ES REAL Y QUÉ NO — esto importa más que el diseño
   -----------------------------------------------------
   Aceptar y Rechazar SÍ escriben: llaman a /api/resolver, que ya existía y es
   el mismo que usa la tabla de siempre. Lo que se pulsa aquí queda en
   salida/ofertas.json igual que antes.

   Enviar una respuesta de texto al cliente NO existe: no hay endpoint que
   mande nada a nadie. Por eso el compositor va marcado como demo y su botón
   no finge que envía. Inventarme un "enviado" seria mentir en la unica parte
   de la pantalla donde se supone que hablas tu.

   LA RESPUESTA SUGERIDA
   ---------------------
   No se le pide a ningun modelo: se arma con los campos que la REGLA ya
   decidio para esa oferta -su decision, su motivo, el minimo aceptable y el
   descuento maximo automatico-. Por eso se puede explicar por que la sugiere:
   el "por que" es literalmente el campo `motivo` que escribio 04_ofertas.py.
   Y es editable, porque quien cierra el trato eres tu. */

const COLUMNAS = [
  ['recibidas', 'Recibidas', 'neutro', () => true],
  ['negociacion', 'En negociación', 'aviso',
   (o) => o.estado === 'pendiente' || o.decision === 'A_MANO'
          || o.decision === 'CONTRAOFERTA'],
  ['aceptadas', 'Aceptadas', 'bien', (o) => o.decision === 'ACEPTAR'],
  ['rechazadas', 'Rechazadas', 'critico', (o) => o.decision === 'RECHAZAR'],
];

/* Cuántas tarjetas se ven en cada columna antes de plegar. Tres es lo que
   hace que las cuatro columnas midan lo mismo con el reparto que hay hoy. */
const TOPE = 3;

const TONO_DECISION = {
  ACEPTAR: ['p-ok', 'aceptada'],
  RECHAZAR: ['p-rojo', 'rechazada'],
  A_MANO: ['p-ambar', 'espera tu decisión'],
  CONTRAOFERTA: ['p-violeta', 'contraoferta'],
};

let OFERTAS = [];
let ABIERTA = null;

const fecha = (s) => {
  if (!s) return '';
  const d = new Date(s);
  return isNaN(d) ? String(s).slice(0, 16)
    : d.toLocaleString('es-ES', {day: '2-digit', month: '2-digit',
                                hour: '2-digit', minute: '2-digit'});
};

/* ------------------------------------------------------ la respuesta sugerida
   Se arma con lo que la regla ya decidio. Ni una frase inventada sobre la
   pieza: los importes salen de la propia oferta. */
function sugerida(o) {
  const imp = eur(o.importe);
  const lista = o.precio_lista ? eur(o.precio_lista) : null;
  const pieza = o.descripcion || ('la pieza ' + (o.id_pieza || ''));

  if (o.decision === 'ACEPTAR') {
    return `Hola:\n\nTrato hecho por ${pieza}: te la dejo en ${imp} + IVA.\n\n`
      + `Dime cómo la quieres, si la recoges o te la enviamos, y te la preparo.\n\n`
      + `Un saludo`;
  }
  if (o.decision === 'RECHAZAR') {
    const min = o.minimo_aceptable ? eur(o.minimo_aceptable) : null;
    return `Hola:\n\nPor ${pieza} no puedo llegar a ${imp}.\n\n`
      + (min ? `Lo más ajustado que puedo hacerte son ${min} + IVA.\n\n` : '')
      + `Si te encaja, me dices y te la reservo.\n\nUn saludo`;
  }
  // A_MANO y contraoferta: la regla no cierra, asi que el borrador no cierra
  // tampoco. Deja la puerta abierta sin comprometer un precio.
  const tope = o.descuento_max_automatico != null
    ? ' (la regla cierra sola hasta un ' + pct(o.descuento_max_automatico) + ')'
    : '';
  return `Hola:\n\nHe visto tu oferta de ${imp} por ${pieza}`
    + (lista ? `, que está publicada a ${lista}` : '') + `.\n\n`
    + `Dame un momento que lo miro y te digo algo hoy mismo${tope}.\n\n`
    + `Un saludo`;
}

function porQue(o) {
  if (o.motivo) return o.motivo;
  if (o.decision === 'A_MANO') return 'la regla no la cierra sola: la decides tú';
  return 'sin motivo registrado';
}

/* ------------------------------------------------------------- la tarjeta */
function tarjeta(o) {
  const t = crear('article', 'of-tarjeta');
  t.tabIndex = 0;
  t.setAttribute('role', 'button');
  t.setAttribute('aria-label', 'Abrir la oferta ' + o.n);

  const cab = crear('div', 'of-cab');
  const [clase, texto] = TONO_DECISION[o.decision] || ['p-gris', o.decision || '—'];
  cab.append(crear('span', 'pastilla ' + clase, texto),
             crear('span', 'of-fecha', fecha(o.fecha)));
  t.append(cab);

  t.append(crear('p', 'of-pieza', o.descripcion || ('Pieza ' + (o.id_pieza || '—'))));
  t.append(crear('p', 'of-cliente', o.cliente || 'anónimo'));

  const cifras = crear('div', 'of-cifras');
  if (o.precio_lista) cifras.append(crear('span', 'of-lista', eur(o.precio_lista)));
  cifras.append(crear('b', 'of-importe', eur(o.importe)));
  if (o.descuento != null) {
    cifras.append(crear('span', 'of-dto', '−' + pct(o.descuento)));
  }
  t.append(cifras);

  // Acciones rapidas. Solo se ofrecen donde de verdad se puede actuar: una
  // oferta ya cerrada no se vuelve a decidir, y un boton que no hace nada es
  // peor que no tenerlo.
  const acc = crear('div', 'of-acciones');
  const ver = crear('button', 'boton mini sutil', 'Responder');
  ver.type = 'button';
  ver.onclick = (ev) => { ev.stopPropagation(); abrirDrawer(o.n); };
  acc.append(ver);

  if (o.estado === 'pendiente') {
    const si = crear('button', 'boton mini', 'Aceptar');
    const no = crear('button', 'boton mini peligro', 'Rechazar');
    si.type = no.type = 'button';
    si.onclick = (ev) => { ev.stopPropagation(); decidir(o.n, 'ACEPTAR', si); };
    no.onclick = (ev) => { ev.stopPropagation(); decidir(o.n, 'RECHAZAR', no); };
    acc.append(si, no);
  } else {
    acc.append(crear('span', 'of-cerrada',
      'cerrada por ' + (o.resuelta_por || 'la regla')));
  }
  t.append(acc);

  t.onclick = () => abrirDrawer(o.n);
  t.onkeydown = (ev) => {
    if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); abrirDrawer(o.n); }
  };
  return t;
}

/* ------------------------------------------------------------- el tablero */
function pintarTablero() {
  const destino = $('#of-tablero');
  if (!destino) return;

  if (!OFERTAS.length) {
    const v = crear('div', 'estado-vacio');
    v.append(crear('strong', null, 'Todavía no ha entrado ninguna oferta.'),
             document.createTextNode(' Lanza una arriba y aparece aquí.'));
    destino.replaceChildren(v);
    return;
  }

  destino.replaceChildren(...COLUMNAS.map(([clave, titulo, tono, filtro]) => {
    const lista = OFERTAS.filter(filtro);
    const col = crear('div', 'of-col of-' + tono);
    const cab = crear('div', 'of-col-cab');
    cab.append(crear('span', 'of-col-t', titulo),
               crear('b', 'of-col-n', String(lista.length)));
    col.append(cab);

    const cuerpo = crear('div', 'of-col-cuerpo');
    if (!lista.length) {
      cuerpo.append(crear('p', 'of-col-vacia', 'Ninguna'));
    } else {
      // Recibidas se ordena por fecha; el resto conserva el orden del fichero.
      const orden = clave === 'recibidas'
        ? [...lista].sort((a, b) => String(b.fecha).localeCompare(String(a.fecha)))
        : lista;
      orden.forEach((o, i) => {
        const t = tarjeta(o);
        if (i >= TOPE) t.classList.add('of-oculta');
        cuerpo.append(t);
      });
    }
    col.append(cuerpo);

    // Compacto por defecto. Las cuatro columnas reparten 15 · 5 · 9 · 1, así
    // que sin tope la de "Recibidas" mide quince tarjetas y la de
    // "Rechazadas" una: eso no es una rejilla, son cuatro columnas sueltas de
    // alturas distintas. Con el tope las cuatro miden lo mismo y lo que
    // sobra está a un clic, no escondido.
    if (lista.length > TOPE) {
      const mas = crear('button', 'of-mas');
      mas.type = 'button';
      mas.setAttribute('aria-expanded', 'false');
      const restantes = lista.length - TOPE;
      mas.textContent = 'Ver ' + restantes + (restantes === 1 ? ' más' : ' más');
      mas.onclick = () => {
        const abierta = mas.getAttribute('aria-expanded') === 'true';
        cuerpo.querySelectorAll('.of-tarjeta').forEach((t, i) => {
          t.classList.toggle('of-oculta', !abierta && i >= TOPE);
        });
        mas.setAttribute('aria-expanded', abierta ? 'false' : 'true');
        mas.textContent = abierta ? 'Ver ' + restantes + ' más' : 'Ver menos';
      };
      col.append(mas);
    }
    return col;
  }));
}

/* --------------------------------------------------------------- el drawer */
function cerrarDrawer() {
  const d = $('#of-drawer');
  if (!d) return;
  d.classList.remove('abierto');
  d.setAttribute('aria-hidden', 'true');
  const velo = $('#of-velo');
  if (velo) velo.hidden = true;
  ABIERTA = null;
}

function linea(hito, cuando, texto, tono) {
  const l = crear('li', 'tl-linea' + (tono ? ' tl-' + tono : ''));
  l.append(crear('span', 'tl-punto'));
  const c = crear('div');
  c.append(crear('b', null, hito));
  if (cuando) c.append(crear('span', 'tl-cuando', cuando));
  if (texto) c.append(crear('p', 'tl-txt', texto));
  l.append(c);
  return l;
}

function abrirDrawer(n) {
  const o = OFERTAS.find((x) => x.n === n);
  const d = $('#of-drawer');
  if (!o || !d) return;
  ABIERTA = n;

  const cuerpo = $('#of-drawer-cuerpo');
  cuerpo.replaceChildren();

  /* --- cabecera --- */
  const [clase, texto] = TONO_DECISION[o.decision] || ['p-gris', o.decision || '—'];
  const cab = crear('div', 'dr-cab');
  cab.append(crear('span', 'pastilla ' + clase, texto));
  cuerpo.append(cab);
  cuerpo.append(crear('h3', 'dr-pieza', o.descripcion || ('Pieza ' + o.id_pieza)));
  cuerpo.append(crear('p', 'dr-cliente', (o.cliente || 'anónimo')
    + ' · nº ' + o.n + (o.id_pieza ? ' · pieza ' + o.id_pieza : '')));

  /* --- las cifras, tal cual estan en la oferta --- */
  const rej = crear('div', 'dr-cifras');
  [['Publicado', o.precio_lista != null ? eur(o.precio_lista) : '—'],
   ['Ofrece', eur(o.importe)],
   ['Descuento', o.descuento != null ? pct(o.descuento) : '—'],
   ['Mínimo aceptable', o.minimo_aceptable != null ? eur(o.minimo_aceptable) : '—'],
   ['Antigüedad', o.antiguedad || '—'],
   ['Tope automático', o.descuento_max_automatico != null
     ? pct(o.descuento_max_automatico) : '—'],
  ].forEach(([k, v]) => {
    const c = crear('div', 'dr-dato');
    c.append(crear('span', 'dr-k', k), crear('b', 'dr-v', v));
    rej.append(c);
  });
  cuerpo.append(rej);

  /* --- el historico. Solo hitos con fecha o dato real detras --- */
  cuerpo.append(crear('h4', 'dr-titulo', 'Histórico'));
  const tl = crear('ul', 'timeline');
  tl.append(linea('Entra la oferta', fecha(o.fecha),
    (o.cliente || 'Un cliente') + ' ofrece ' + eur(o.importe)
    + (o.precio_lista ? ' por una pieza publicada a ' + eur(o.precio_lista) : ''),
    'neutro'));
  tl.append(linea('La regla la mira', '', porQue(o), 'pregunta'));
  if (o.estado === 'pendiente') {
    tl.append(linea('Esperando tu decisión', '',
      'la regla no la cierra sola: pasa a tu mesa', 'aviso'));
  } else {
    tl.append(linea('Cerrada', '',
      'resuelta por ' + (o.resuelta_por || 'la regla'),
      o.decision === 'RECHAZAR' ? 'critico' : 'bien'));
  }
  cuerpo.append(tl);

  /* --- el compositor --- */
  cuerpo.append(crear('h4', 'dr-titulo', 'Respuesta sugerida'));
  const razon = crear('p', 'dr-razon');
  razon.append(crear('b', null, 'Por qué esta: '),
               document.createTextNode(porQue(o)));
  cuerpo.append(razon);

  const ta = crear('textarea', 'dr-texto');
  ta.rows = 8;
  ta.value = sugerida(o);
  ta.setAttribute('aria-label', 'Respuesta al cliente, editable');
  cuerpo.append(ta);

  const pieAcc = crear('div', 'dr-acciones');
  const enviar = crear('button', 'boton', 'Enviar respuesta');
  enviar.type = 'button';
  enviar.onclick = () => {
    const aviso = crear('p', 'dr-demo-aviso');
    aviso.textContent = 'Esto no envía nada: VendIQ no tiene integración viva con '
      + 'WhatsApp ni con el correo. El texto es tuyo, cópialo y mándalo tú.';
    pieAcc.after(aviso);
    enviar.disabled = true;
  };
  pieAcc.append(enviar, crear('span', 'dr-demo', 'demo — no envía'));

  if (o.estado === 'pendiente') {
    const si = crear('button', 'boton mini', 'Aceptar oferta');
    const no = crear('button', 'boton mini peligro', 'Rechazar');
    si.type = no.type = 'button';
    si.onclick = () => decidir(o.n, 'ACEPTAR', si);
    no.onclick = () => decidir(o.n, 'RECHAZAR', no);
    const reales = crear('div', 'dr-reales');
    reales.append(crear('p', 'dr-reales-t',
      'Esto sí se guarda de verdad:'), si, no);
    cuerpo.append(pieAcc, reales);
  } else {
    cuerpo.append(pieAcc);
  }

  d.classList.add('abierto');
  d.setAttribute('aria-hidden', 'false');
  const velo = $('#of-velo');
  if (velo) velo.hidden = false;
  const cerrar = $('#of-cerrar');
  if (cerrar) cerrar.focus();
}

/* ------------------------------------------ aceptar y rechazar, de verdad */
async function decidir(n, decision, boton) {
  if (boton) { boton.disabled = true; boton.textContent = '…'; }
  try {
    await api('/api/resolver', {n, decision});
    await cargar();                       // se relee: no se toca el objeto local
    if (ABIERTA === n) abrirDrawer(n);
  } catch (e) {
    if (boton) { boton.disabled = false; boton.textContent = 'Reintentar'; }
    const d = $('#of-drawer-cuerpo');
    if (d) d.append(Object.assign(crear('p', 'dr-demo-aviso'),
      {textContent: 'No se pudo guardar: ' + e.message}));
  }
}

/* -------------------------------------------------------------- arranque */
async function cargar() {
  try {
    const d = await api('/api/ofertas');
    OFERTAS = Array.isArray(d) ? d : (d.ofertas || []);
  } catch (e) {
    const t = $('#of-tablero');
    if (t) t.replaceChildren(Object.assign(crear('div', 'estado-vacio fallo'),
      {textContent: 'No se pudieron leer las ofertas: ' + e.message}));
    return;
  }
  pintarTablero();
}

if ($('#of-tablero')) {
  const cerrar = $('#of-cerrar');
  if (cerrar) cerrar.onclick = cerrarDrawer;
  const velo = $('#of-velo');
  if (velo) velo.onclick = cerrarDrawer;
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && ABIERTA !== null) cerrarDrawer();
  });
  cargar();
}
