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

   POR QUÉ NO ES UN SVG
   La primera versión eran cuatro columnas en un SVG de 1.180 px. Cuatro columnas
   con texto legible no bajan de ~950 px, así que en cuanto la ventana se
   estrechaba había que deslizar — y un diagrama que hay que deslizar no se lee de
   un vistazo, que es justo para lo que sirve. En bandas apiladas de HTML cada
   fila refluye sola: cuatro tarjetas, luego dos, luego una. Nunca desliza y no
   se pierde ni una palabra.

   CANALES NO CONECTADOS
   Gmail, Wallapop y el resto van con borde DISCONTINUO y en gris de texto, nunca
   en un color de la paleta. No son una categoría más: son una ausencia. Hoy solo
   entra WhatsApp, y pintarlos igual sería enseñar una capacidad que no existe.
========================================================================== */

/* Una tarjeta del recorrido. `tono` pinta el borde y la cifra; `apagado` la deja
   discontinua y en gris, que es como se dibuja lo que no está conectado. */
function nodoFlujo(o) {
  const caja = crear('div', 'nodo' + (o.apagado ? ' apagado' : ''));
  if (o.tono) caja.style.borderColor = o.tono;

  const cab = crear('p', 'nodo-cab');
  cab.append(crear('span', 'nodo-t', o.titulo));
  if (o.cifra) {
    const c = crear('span', 'nodo-c', o.cifra);
    if (o.tono) c.style.color = o.tono;
    cab.append(c);
  }
  caja.append(cab);
  if (o.pie) caja.append(crear('p', 'nodo-p', o.pie));
  if (o.pie2) caja.append(crear('p', 'nodo-p', o.pie2));
  return caja;
}

function bandaFlujo(n, titulo, ancho, nodos) {
  const b = crear('div', 'flujo-banda');
  b.append(crear('p', 'flujo-titulo', n + ' · ' + titulo));
  const fila = crear('div', 'flujo-fila ' + ancho);
  nodos.forEach(function (x) { fila.append(x); });
  b.append(fila);
  return b;
}

function pintarRecorrido(a, motor) {
  const acc = a.acciones;
  const total = Object.values(acc).reduce(function (x, y) { return x + y; }, 0);
  const caja = crear('div', 'flujo');

  /* --------------------------------------------------- 1 · por dónde entra */
  caja.append(bandaFlujo(1, 'Entra por', 'cuatro', [
    nodoFlujo({titulo: 'WhatsApp', cifra: miles(a.resumen.conversaciones),
               pie: 'el único conectado', tono: 'var(--cian)'}),
    nodoFlujo({titulo: 'Gmail', pie: 'no conectado', apagado: true}),
    nodoFlujo({titulo: 'Wallapop', pie: 'no conectado', apagado: true}),
    nodoFlujo({titulo: 'Otras plataformas', pie: 'no conectado', apagado: true}),
  ]));
  caja.append(crear('div', 'flujo-baja'));

  /* -------------------------------------------------------- 2 · dónde busca */
  caja.append(bandaFlujo(2, 'Busca en', 'dos', [
    nodoFlujo({titulo: 'La base de conocimiento',
               cifra: miles(motor.fichas_indexadas) + ' fichas',
               pie: miles(motor.piezas_catalogo) + ' piezas del catálogo y las '
                    + 'políticas de la empresa, en el mismo índice',
               tono: 'var(--cian)'}),
    nodoFlujo({titulo: 'Búsqueda híbrida',
               cifra: motor.peso_lexico + ' + ' + motor.peso_semantico,
               pie: 'palabras pesadas por IDF más significado del modelo, en una '
                    + 'sola fórmula que ordena piezas y políticas por igual',
               tono: 'var(--cian)'}),
  ]));
  caja.append(crear('div', 'flujo-baja'));

  /* ------------------------------------------------------ 3 · con qué filtra */
  caja.append(bandaFlujo(3, 'Filtra con', 'cuatro', [
    nodoFlujo({titulo: 'Código exacto',
               pie: 'si el mensaje trae un nº de stock, esa ficha gana y se acabó'}),
    nodoFlujo({titulo: 'Compatibilidad',
               pie: 'descarta la marca, el modelo, el núcleo y el lado que no son'}),
    nodoFlujo({titulo: 'Umbral de confianza',
               cifra: motor.umbral_pieza + ' / ' + motor.umbral_politica,
               pie: 'por debajo no se ofrece nada: la lista sale vacía'}),
    nodoFlujo({titulo: 'Cerrojo del precio',
               cifra: String(motor.umbral_precio),
               pie: 'más alto a propósito, y además la pieza tiene que estar '
                    + 'disponible. Si no, el importe no llega al redactor'}),
  ]));
  caja.append(crear('div', 'flujo-baja'));

  /* --------------------------------------------------------- 4 · dónde acaba */
  const salidas = [
    ['RESPONDER', 'Contesta solo', 'var(--cian)',
     'tiene la ficha y la respuesta sale sin que nadie mire'],
    ['PREGUNTAR', 'Pregunta cuál', 'var(--violeta)',
     'varias piezas encajan: pregunta con botones del catálogo'],
    ['ESCALAR', 'A tu mesa', 'var(--ambar)',
     'no está seguro o es una decisión de negocio: la ve una persona'],
  ];
  caja.append(bandaFlujo(4, 'Acaba en', 'tres', salidas.map(function (s) {
    const n = acc[s[0]] || 0;
    return nodoFlujo({titulo: s[1], cifra: miles(n) + ' · ' + pct(n / total),
                      pie: s[3], tono: s[2]});
  })));

  const pie = crear('p', 'flujo-pie');
  pie.textContent = 'Los umbrales se leen del motor en marcha (03_buscar.py); los '
    + 'volúmenes, de los ' + a.parametros.dias + ' días medidos. Ni un número '
    + 'escrito a mano.';
  caja.append(pie);

  $('#diagrama').replaceChildren(caja);
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
