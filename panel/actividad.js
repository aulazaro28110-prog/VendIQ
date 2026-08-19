/* VendIQ · actividad del centro de control
   ------------------------------------------------------------------------
   Pinta salida/actividad.json, que genera 10_simular.py pasando días enteros
   de tráfico por el sistema real. Aquí no se calcula ni un número: todos
   vienen medidos.

   COLOR
   -----
   Tres categorías y dos estados, con los tokens ya validados contra el fondo
   real (#06080c). El orden es fijo y no rota: RESPONDER siempre cian,
   PREGUNTAR siempre violeta, ESCALAR siempre ámbar. Si mañana desaparece una
   categoría, las otras dos NO cambian de color — un gráfico que se repinta al
   filtrar es un gráfico en el que no se puede confiar.

   El rojo no aparece en ningún reparto: está reservado para errores de verdad
   (una fuga de precio). Y nunca va pegado al ámbar, porque un deuteranope los
   distingue con un ΔE de 3,8 sobre un mínimo de 8. */

const COLOR_ACCION = {
  RESPONDER: {token: 'var(--cian)',    clase: 'seg-ok',      etiqueta: 'Responde'},
  PREGUNTAR: {token: 'var(--violeta)', clase: 'seg-pregunta', etiqueta: 'Pregunta cuál'},
  ESCALAR:   {token: 'var(--ambar)',   clase: 'seg-nada',     etiqueta: 'A tu mesa'},
};
const miles = (n) => n.toLocaleString('es-ES');

/* ------------------------------------------------------- la declaración */
function pintarDeclaracion(a) {
  const caja = $('#declaracion');
  const r = a.resumen;
  caja.replaceChildren();
  const t = crear('p', 'declaracion-titulo', 'Datos sintéticos, medidas reales');
  const c = crear('p', 'declaracion-cuerpo');
  c.textContent = `${a.aviso} ${a.mezcla_declarada}`;
  const pie = crear('p', 'declaracion-pie');
  pie.textContent = `${miles(r.conversaciones)} conversaciones y ` +
    `${miles(r.mensajes)} mensajes ejecutados en ` +
    `${a.segundos_de_ejecucion} s contra ${miles(a.catalogo.piezas)} piezas · ` +
    `generado el ${a.generado} por 10_simular.py`;
  caja.append(t, c, pie);
}

/* ------------------------------------------------------------ los KPIs */
function pintarKPIsActividad(a) {
  const r = a.resumen;
  const fugas = r.fugas_de_precio;
  const tiles = [
    ['Conversaciones medidas', miles(r.conversaciones), '',
     `${miles(r.mensajes)} mensajes en ${a.parametros.dias} días`, 'acento'],
    ['Resueltas sin persona', pct(r.tasa_resolucion), '',
     `${miles(r.escaladas)} llegaron a tu mesa`, 'acento'],
    ['Tiempo de respuesta', r.ms_mediana, 'ms',
     `p95 ${r.ms_p95} ms · máximo ${r.ms_max} ms`, 'acento'],
    ['Precios dados solos', miles(r.precios_dados), '',
     'sin que tú mires ninguno', 'acento'],
    ['Fugas de precio', fugas, '',
     fugas ? 'REVISA salida/actividad.json' : 'ni un importe sin autorizar',
     fugas ? 'malo' : 'acento'],
  ];
  $('#kpis').replaceChildren(...tiles.map(([et, cifra, unidad, nota, clase]) => {
    const caja = crear('div', 'ind ' + clase);
    caja.append(crear('p', 'etiqueta', et));
    const c = crear('p', 'cifra', String(cifra));
    if (unidad) c.append(crear('span', 'unidad', unidad));
    caja.append(c, crear('p', 'nota', nota));
    return caja;
  }));
}

/* --------------------------------------------------------- barras/día */
function pintarDias(a) {
  const dias = a.por_dia;
  const max = Math.max(...dias.map((d) => d.conversaciones), 1);
  const caja = crear('div', 'g-barras-v');

  dias.forEach((d) => {
    const col = crear('div', 'col-dia');
    const pila = crear('div', 'pila');
    pila.style.height = `${(d.conversaciones / max) * 100}%`;

    if (d.conversaciones) {
      // Dos segmentos, con 2px de hueco entre ellos: sin el hueco, dos rellenos
      // pegados se leen como una sola barra de un color intermedio.
      const esc = crear('div', 'seg-esc');
      esc.style.flex = String(d.escaladas);
      const res = crear('div', 'seg-res');
      res.style.flex = String(d.resueltas);
      pila.append(esc, res);
      pila.title = `${d.dia} ${d.fecha}\n${d.conversaciones} conversaciones\n` +
        `${d.resueltas} resueltas · ${d.escaladas} a tu mesa\n` +
        `mediana ${d.ms_mediana} ms`;
    } else {
      pila.classList.add('cerrado');
      pila.style.height = '3px';
      pila.title = `${d.dia} ${d.fecha} · cerrado`;
    }

    // Etiqueta directa solo en el día de más volumen: un número encima de cada
    // barra es ruido, y el resto se lee al pasar el ratón.
    if (d.conversaciones === max) {
      const v = crear('span', 'valor-encima', String(d.conversaciones));
      col.append(v);
    }
    col.append(pila, crear('span', 'etiqueta-x', d.fecha.slice(8) + '/' +
                           d.fecha.slice(5, 7)));
    caja.append(col);
  });
  $('#g-dias').replaceChildren(caja);

  $('#leyenda-dias').replaceChildren(...[
    ['Resueltas sin persona', 'var(--cian)'],
    ['A tu mesa', 'var(--ambar)'],
  ].map(([texto, color]) => {
    const li = crear('span');
    const punto = crear('i');
    punto.style.background = color;
    li.append(punto, document.createTextNode(texto));
    return li;
  }));

  $('#tabla-dias').replaceChildren(...dias.map((d) => {
    const tr = crear('tr');
    tr.append(crear('td', '', `${d.dia} ${d.fecha}`),
              crear('td', 'num', String(d.conversaciones)),
              crear('td', 'num', String(d.mensajes)),
              crear('td', 'num', String(d.resueltas)),
              crear('td', 'num', String(d.escaladas)),
              crear('td', 'num', d.ms_mediana === null ? '—' : String(d.ms_mediana)));
    return tr;
  }));
}

/* ------------------------------------------------------------- horas */
function pintarHoras(a) {
  const max = Math.max(...a.por_hora.map((h) => h.conversaciones), 1);
  const caja = crear('div', 'g-barras-v horas');
  a.por_hora.forEach((h) => {
    const col = crear('div', 'col-dia');
    const barra = crear('div', 'pila una');
    barra.style.height = `${(h.conversaciones / max) * 100}%`;
    barra.title = `${h.hora}:00 — ${h.conversaciones} conversaciones`;
    col.append(barra, crear('span', 'etiqueta-x', String(h.hora)));
    caja.append(col);
  });
  $('#g-horas').replaceChildren(caja);
}

/* ----------------------------------------------------------- acciones */
function pintarAcciones(a) {
  const total = Object.values(a.acciones).reduce((x, y) => x + y, 0);
  // Orden FIJO, no por tamaño: si el reparto cambia, los colores no bailan.
  const orden = ['RESPONDER', 'PREGUNTAR', 'ESCALAR']
    .filter((k) => a.acciones[k]);

  $('#seg-acciones').replaceChildren(...orden.map((k) => {
    const n = a.acciones[k];
    const seg = crear('div', COLOR_ACCION[k].clase,
                      n > total * 0.07 ? pct(n / total) : '');
    seg.style.flex = String(n);
    seg.title = `${COLOR_ACCION[k].etiqueta}: ${miles(n)} mensajes`;
    return seg;
  }));

  $('#leyenda-acciones').replaceChildren(...orden.map((k) => {
    const li = crear('span');
    const punto = crear('i');
    punto.style.background = COLOR_ACCION[k].token;
    li.append(punto, document.createTextNode(
      `${COLOR_ACCION[k].etiqueta} — ${miles(a.acciones[k])}`));
    return li;
  }));

  const motivos = a.motivos_escalado || [];
  const max = Math.max(...motivos.map((m) => m.veces), 1);
  $('#g-motivos').replaceChildren(...motivos.map((m) => {
    const b = crear('div', 'barra');
    const fila = crear('div', 'fila');
    fila.append(crear('span', 'nombre', m.motivo),
                crear('span', 'valor', miles(m.veces)));
    const canal = crear('div', 'canal');
    const relleno = crear('div', 'relleno');
    relleno.style.width = `${(m.veces / max) * 100}%`;
    relleno.style.background = 'var(--ambar)';
    canal.append(relleno);
    b.append(fila, canal);
    return b;
  }));
}

/* ------------------------------------------------- barras horizontales
   Magnitud de una sola medida repartida por categorías: UN solo tono, no una
   paleta categórica. Poner un color por barra sugeriría que cada fila es una
   entidad distinta que se puede seguir entre gráficos, y no lo es. */
function barrasHorizontales(destino, filas, color) {
  const max = Math.max(...filas.map((f) => f[1]), 1);
  $(destino).replaceChildren(...filas.map(([nombre, n, pie]) => {
    const b = crear('div', 'barra');
    const fila = crear('div', 'fila');
    fila.append(crear('span', 'nombre', nombre),
                crear('span', 'valor', pie || miles(n)));
    const canal = crear('div', 'canal');
    const relleno = crear('div', 'relleno');
    relleno.style.width = `${(n / max) * 100}%`;
    relleno.style.background = color;
    canal.append(relleno);
    b.append(fila, canal);
    return b;
  }));
}

/* ------------------------------------------------------- intenciones */
function pintarIntenciones(a) {
  const total = Object.values(a.intenciones).reduce((x, y) => x + y, 0);
  const filas = Object.entries(a.intenciones)
    .sort((x, y) => y[1] - x[1])
    .map(([k, n]) => [k, n, `${miles(n)} · ${pct(n / total)}`]);
  barrasHorizontales('#g-intenciones', filas, 'var(--cian)');
}

/* ----------------------------------------------------------- precios
   El orden es el mismo que en las acciones (cian → violeta → ámbar) para que
   los dos gráficos se lean igual, y porque esa adyacencia ya está validada:
   el ámbar nunca toca al rojo, que aquí no aparece. */
function pintarPrecios(a) {
  const p = a.precios;
  const orden = [
    ['publicable',     'Dicho por el bot',   'seg-ok',       'var(--cian)'],
    ['confianza_baja', 'No estaba seguro',   'seg-pregunta', 'var(--violeta)'],
    ['sin_confirmar',  'Lo confirmas tú',    'seg-nada',     'var(--ambar)'],
  ].filter(([k]) => p[k]);
  const total = orden.reduce((s, [k]) => s + p[k], 0);

  $('#seg-precios').replaceChildren(...orden.map(([k, etiqueta, clase]) => {
    const seg = crear('div', clase, p[k] > total * 0.07 ? pct(p[k] / total) : '');
    seg.style.flex = String(p[k]);
    seg.title = `${etiqueta}: ${miles(p[k])}`;
    return seg;
  }));

  $('#leyenda-precios').replaceChildren(...orden.map(([k, etiqueta, , token]) => {
    const li = crear('span');
    const punto = crear('i');
    punto.style.background = token;
    li.append(punto, document.createTextNode(`${etiqueta} — ${miles(p[k])}`));
    return li;
  }));

  const retenidos = (p.sin_confirmar || 0) + (p.confianza_baja || 0);
  $('#nota-precios').textContent =
    `De ${miles(total)} importes que aparecieron, el bot se calló ${miles(retenidos)}. ` +
    `No es que decidiera callarse: esos precios no entran en el texto que redacta, ` +
    `así que no puede decirlos. Fugas medidas: ${a.resumen.fugas_de_precio}.`;
}

/* ------------------------------------------------------- lo no cubierto */
function pintarAtasco(a) {
  const filas = (a.no_cubierto || []).slice(0, 8)
    .map((c) => [c.consulta, c.veces, `${c.veces} veces`]);
  if (!filas.length) {
    $('#g-atasco').replaceChildren(
      crear('p', 'nota', 'Ninguna consulta se repitió sin resolverse.'));
    return;
  }
  barrasHorizontales('#g-atasco', filas, 'var(--ambar)');
}

/* ------------------------------------------------------------ muestra */
function pintarMuestra(a) {
  const conv = (a.muestra || []).filter((m) => !m.FUGA).slice(0, 6);
  $('#muestra-conv').replaceChildren(...conv.map((c) => {
    const caja = crear('div', 'conv-muestra');
    const cab = crear('div', 'conv-cab');
    cab.append(crear('span', 'pastilla p-gris', c.situacion),
               crear('span', 'conv-hora', c.hora || ''));
    caja.append(cab);
    c.turnos.forEach((t) => {
      const par = crear('div', 'conv-turno');
      par.append(crear('p', 'conv-cliente', t.cliente));
      t.bot.forEach((l) => par.append(crear('p', 'conv-bot', l)));
      par.append(crear('span', 'conv-meta', `${t.accion} · ${t.ms} ms`));
      caja.append(par);
    });
    return caja;
  }));
}

/* ---------------------------------------------------------------- init */
async function cargarActividad() {
  let a;
  try {
    [a, MOTOR] = await Promise.all([api('/api/actividad'),
                                   api('/api/estado')]);
  } catch {
    return;                       // sin datos aún: el resto del panel funciona
  }
  if (!a || !a.resumen) return;
  ACTIVIDAD = a;
  ACTIVIDAD_LISTA = true;
  pintarHeroActividad(a);
  pintarDeclaracion(a);
  pintarKPIsActividad(a);
  pintarDias(a);
  pintarHoras(a);
  pintarAcciones(a);
  pintarIntenciones(a);
  pintarPrecios(a);
  pintarAtasco(a);
  pintarMuestra(a);
  pintarRecorrido(a, MOTOR.sistema);
}

let ACTIVIDAD = null;
let MOTOR = null;

/* ==========================================================================
   EL RECORRIDO DE UN MENSAJE
   --------------------------------------------------------------------------
   Cuatro bandas: por dónde entra, dónde busca, con qué filtra y dónde acaba.
   Ni un número escrito a mano — los umbrales salen de /api/estado (que los lee
   de 03_buscar.py) y los volúmenes de actividad.json.

   CANALES NO CONECTADOS
   Gmail, Wallapop y el resto van PUNTEADOS y en gris de texto, nunca en un
   color de la paleta. No son una categoría más: son una ausencia. Hoy solo
   entra WhatsApp, y pintarlos igual sería enseñar una capacidad que no existe.
========================================================================== */

const SVGNS = 'http://www.w3.org/2000/svg';
const svgEl = (tag, attrs) => {
  const el = document.createElementNS(SVGNS, tag);
  for (const k in (attrs || {})) el.setAttribute(k, attrs[k]);
  return el;
};

/* Una caja con título, cifra opcional y hasta dos líneas de pie. Devuelve sus
   anclas para que las flechas no dependan de coordenadas escritas a mano. */
function cajaSVG(padre, o) {
  const g = svgEl('g');
  const r = svgEl('rect', {x: o.x, y: o.y, width: o.w, height: o.h, rx: 12,
                           fill: o.punteada ? 'none' : '#0b0e14',
                           stroke: o.color, 'stroke-width': o.punteada ? 1.2 : 1.4});
  if (o.punteada) r.setAttribute('stroke-dasharray', '5 4');
  g.append(r);

  const ty = o.y + (o.pie2 ? 26 : (o.pie ? 27 : o.h / 2 + 5));
  const t = svgEl('text', {x: o.x + 15, y: ty, class: 'dg-titulo'});
  t.textContent = o.titulo;
  g.append(t);

  if (o.cifra) {
    const c = svgEl('text', {x: o.x + o.w - 15, y: ty, class: 'dg-cifra',
                             'text-anchor': 'end', fill: o.color});
    c.textContent = o.cifra;
    g.append(c);
  }
  [o.pie, o.pie2].forEach((texto, i) => {
    if (!texto) return;
    const p = svgEl('text', {x: o.x + 15, y: ty + 20 + i * 16,
                             class: o.punteada ? 'dg-pie dg-apagado' : 'dg-pie'});
    p.textContent = texto;
    g.append(p);
  });
  padre.append(g);
  return {izq: {x: o.x, y: o.y + o.h / 2}, der: {x: o.x + o.w, y: o.y + o.h / 2},
          x: o.x, y: o.y, w: o.w, h: o.h};
}

/* Curva de A a B. El punteado se reserva a lo que NO está conectado. */
function flechaSVG(padre, a, b, o) {
  o = o || {};
  const dx = Math.max(26, (b.x - a.x) * 0.5);
  const p = svgEl('path', {
    d: 'M' + a.x + ' ' + a.y + ' C ' + (a.x + dx) + ' ' + a.y + ', ' +
       (b.x - dx) + ' ' + b.y + ', ' + b.x + ' ' + b.y,
    fill: 'none', stroke: o.color || '#2b3340',
    'stroke-width': o.ancho || 1.4, 'marker-end': 'url(#dg-punta)'});
  if (o.punteada) p.setAttribute('stroke-dasharray', '4 5');
  padre.append(p);
}

/* Conector vertical recto. La curva de arriba asume flujo horizontal: con 18 px
   de caída dibujaría un lazo en vez de una línea. */
function bajadaSVG(padre, x, y1, y2) {
  padre.append(svgEl('path', {d: 'M' + x + ' ' + y1 + ' L' + x + ' ' + y2,
    stroke: DG_LINEA, 'stroke-width': 1.2, fill: 'none',
    'marker-end': 'url(#dg-punta)'}));
}

function bandaSVG(padre, x, texto) {
  const t = svgEl('text', {x: x, y: 22, class: 'dg-banda'});
  t.textContent = texto;
  padre.append(t);
}

const DG_LINEA = '#2b3340';      // estructura
const DG_APAGADO = '#3a4250';    // borde de lo que no está conectado

function pintarRecorrido(a, motor) {
  const W = 1180, H = 440;
  const acc = a.acciones;
  const svg = svgEl('svg', {viewBox: '0 0 ' + W + ' ' + H, class: 'recorrido',
    role: 'img', 'aria-label':
      'Recorrido de un mensaje. Entra por WhatsApp; Gmail, Wallapop y otras ' +
      'plataformas no están conectadas. Busca en ' + motor.fichas_indexadas +
      ' fichas, filtra con cuatro cerrojos y acaba respondiendo ' + acc.RESPONDER +
      ' veces, preguntando ' + acc.PREGUNTAR + ' y pasando a una persona ' +
      acc.ESCALAR + '.'});

  const defs = svgEl('defs');
  const mk = svgEl('marker', {id: 'dg-punta', markerWidth: 7, markerHeight: 7,
                              refX: 6.5, refY: 3.5, orient: 'auto'});
  mk.append(svgEl('path', {d: 'M0,0 L7,3.5 L0,7 z', fill: '#4a5563'}));
  defs.append(mk);
  svg.append(defs);

  /* --------------------------------------------------- 1 · por dónde entra */
  bandaSVG(svg, 16, 'ENTRA POR');
  const canales = [
    ['WhatsApp', miles(a.resumen.conversaciones) + ' conv.', 'el único conectado',
     'var(--cian)', false],
    ['Gmail', null, 'no conectado', DG_APAGADO, true],
    ['Wallapop', null, 'no conectado', DG_APAGADO, true],
    ['Otras plataformas', null, 'no conectado', DG_APAGADO, true],
  ];
  const nodos = canales.map(function (c, i) {
    return cajaSVG(svg, {x: 16, y: 48 + i * 76, w: 200, h: 58,
                         titulo: c[0], cifra: c[1], pie: c[2],
                         color: c[3], punteada: c[4]});
  });

  /* ------------------------------------------------------- 2 · dónde busca */
  bandaSVG(svg, 292, 'BUSCA EN');
  const busca = cajaSVG(svg, {x: 292, y: 126, w: 258, h: 132,
    titulo: 'La base de conocimiento',
    pie: miles(motor.fichas_indexadas) + ' fichas indexadas',
    pie2: motor.peso_lexico + ' léxico + ' + motor.peso_semantico + ' significado',
    color: 'var(--cian)'});
  const nota = svgEl('text', {x: 307, y: 230, class: 'dg-pie'});
  nota.textContent = 'una fórmula para piezas y políticas';
  svg.append(nota);

  nodos.forEach(function (n, i) {
    flechaSVG(svg, n.der, busca.izq, {punteada: i > 0,
      color: i === 0 ? '#1aa19788' : DG_LINEA, ancho: i === 0 ? 2 : 1.2});
  });

  /* ----------------------------------------------------- 3 · con qué filtra */
  bandaSVG(svg, 592, 'FILTRA CON');
  const cerrojos = [
    ['Código exacto', 'si trae un nº de stock, ese gana'],
    ['Compatibilidad', 'descarta marca, modelo, núcleo y lado'],
    ['Umbral de confianza', 'pieza ≥ ' + motor.umbral_pieza + ' · política ≥ ' + motor.umbral_politica],
    ['Cerrojo del precio', '≥ ' + motor.umbral_precio + ' y disponible, o no sale importe'],
  ];
  const puertas = cerrojos.map(function (c, i) {
    return cajaSVG(svg, {x: 592, y: 48 + i * 76, w: 260, h: 58,
                         titulo: c[0], pie: c[1], color: DG_LINEA});
  });
  puertas.forEach(function (p, i) {
    if (i === 0) { flechaSVG(svg, busca.der, p.izq, {color: '#1aa19788', ancho: 2}); return; }
    const arriba = puertas[i - 1];
    bajadaSVG(svg, arriba.x + 30, arriba.y + arriba.h, p.y);
  });

  /* ------------------------------------------------------ 4 · dónde acaba */
  bandaSVG(svg, 960, 'ACABA EN');
  const total = Object.values(acc).reduce(function (x, y) { return x + y; }, 0);
  const salidas = [
    ['RESPONDER', 'Contesta solo', 'var(--cian)',    '#1aa197bb'],
    ['PREGUNTAR', 'Pregunta cuál', 'var(--violeta)', '#7a81e1bb'],
    ['ESCALAR',   'A tu mesa',     'var(--ambar)',   '#b97f14bb'],
  ];
  salidas.forEach(function (s, i) {
    const n = acc[s[0]] || 0;
    const caja = cajaSVG(svg, {x: 960, y: 52 + i * 102, w: 200, h: 76,
      titulo: s[1], cifra: miles(n), pie: pct(n / total) + ' de los mensajes',
      color: s[2]});
    const centroPila = (puertas[0].y + puertas[3].y + puertas[3].h) / 2;
    flechaSVG(svg, {x: puertas[3].x + puertas[3].w, y: centroPila}, caja.izq,
              {color: s[3], ancho: 2});
  });

  const pie = svgEl('text', {x: 16, y: H - 12, class: 'dg-pie dg-apagado'});
  pie.textContent = 'Umbrales leídos de 03_buscar.py; volúmenes, de los ' +
                    a.parametros.dias + ' días medidos. Ni un número escrito a mano.';
  svg.append(pie);

  $('#diagrama').replaceChildren(svg);
}

/* El hero con las cifras medidas, no con las del snapshot de 30 mensajes. */
function pintarHeroActividad(a) {
  const r = a.resumen;
  $('#hero-pie').textContent =
    `${miles(r.conversaciones)} conversaciones pasadas por el sistema en ` +
    `${a.parametros.dias} días: ${miles(r.resueltas_sin_persona)} se resolvieron ` +
    `sin que tú miraras. Catálogo de ${miles(a.catalogo.piezas)} piezas. ` +
    `Los mensajes son sintéticos; las decisiones y los tiempos, medidos.`;
  const cifras = [
    [pct(r.tasa_resolucion), 'resueltas sin persona'],
    [`${r.ms_mediana} ms`, 'en decidir'],
    [miles(r.precios_dados), 'precios dados solos'],
    [String(r.fugas_de_precio), 'precios sin autorizar'],
  ];
  // Etiqueta primero, cifra despues: se lee que es antes de cuanto vale.
  $('#hero-cifras').replaceChildren(...cifras.map(([valor, que]) => {
    const caja = crear('div');
    caja.append(crear('p', 'que', que), crear('p', 'valor', valor));
    return caja;
  }));

  // Las pastillas de contexto de la cabecera, tambien medidas.
  $('#pil-catalogo').textContent = miles(a.catalogo.piezas) + ' piezas';
  $('#pil-dias').textContent = String(a.parametros.dias);
  $('#pil-generado').textContent = a.generado.slice(0, 10);
}

cargarActividad();
