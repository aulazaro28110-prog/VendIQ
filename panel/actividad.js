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
    a = await api('/api/actividad');
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
  pintarDiagramaActividad(a);
}

let ACTIVIDAD = null;

/* El diagrama de convergencia, alimentado con el tráfico medido. */
function pintarDiagramaActividad(a) {
  const r = a.resumen;
  const svg = `
<svg class="diagrama" viewBox="0 0 720 260" role="img"
     aria-label="${r.conversaciones} conversaciones entran; ${r.resueltas_sin_persona} las resuelve el bot y ${r.escaladas} llegan a tu mesa">
  <defs>
    <marker id="pa" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
      <path d="M0,0 L7,3.5 L0,7 z" fill="#63707f"/>
    </marker>
  </defs>
  ${[0, 1, 2, 3, 4].map((i) => `
    <circle cx="58" cy="${42 + i * 44}" r="13" fill="#10141c" stroke="#262e3a"/>
    <path d="M75 ${42 + i * 44} C 150 ${42 + i * 44}, 190 130, 268 130"
          fill="none" stroke="#262e3a" stroke-width="1.5" marker-end="url(#pa)"/>`).join('')}
  <text x="58" y="248" text-anchor="middle" font-size="12">${miles(r.conversaciones)} conversaciones</text>

  <rect x="276" y="98" width="150" height="64" rx="14" fill="#0b0e14" stroke="var(--cian)"/>
  <text x="351" y="124" text-anchor="middle" font-size="13" class="grande">VendIQ</text>
  <text x="351" y="143" text-anchor="middle" font-size="11">busca · decide · filtra</text>

  <path d="M430 118 C 500 118, 520 62, 588 62" fill="none" stroke="var(--cian)"
        stroke-width="1.8" marker-end="url(#pa)"/>
  <path d="M430 142 C 500 142, 520 198, 588 198" fill="none" stroke="var(--ambar)"
        stroke-width="1.8" marker-end="url(#pa)"/>

  <rect x="596" y="36" width="104" height="52" rx="12" fill="#0b0e14" stroke="#262e3a"/>
  <text x="648" y="58" text-anchor="middle" font-size="17" class="cifra" fill="var(--cian)">${miles(r.resueltas_sin_persona)}</text>
  <text x="648" y="76" text-anchor="middle" font-size="11">resueltas solas</text>

  <rect x="596" y="172" width="104" height="52" rx="12" fill="#0b0e14" stroke="#262e3a"/>
  <text x="648" y="194" text-anchor="middle" font-size="17" class="cifra" fill="var(--ambar)">${miles(r.escaladas)}</text>
  <text x="648" y="212" text-anchor="middle" font-size="11">a tu mesa</text>
</svg>`;
  $('#diagrama').innerHTML = svg;
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
  $('#hero-cifras').replaceChildren(...cifras.map(([valor, que]) => {
    const caja = crear('div');
    caja.append(crear('p', 'valor', valor), crear('p', 'que', que));
    return caja;
  }));
}

cargarActividad();
