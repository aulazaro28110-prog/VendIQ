/* VendIQ · Centro de control
   Todo lo que se pinta viene del servidor, que lo saca de ejecutar el buscador y el
   motor de ofertas reales. No hay ni un dato escrito a mano. */

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const crear = (tag, clase, texto) => {
  const el = document.createElement(tag);
  if (clase) el.className = clase;
  if (texto !== undefined) el.textContent = texto;
  return el;
};
const pct = (x) => `${Math.round(x * 100)}%`;
const eur = (x) => `${x.toLocaleString('es-ES', {minimumFractionDigits: 2,
                                                 maximumFractionDigits: 2})} €`;

async function api(ruta, cuerpo) {
  const r = await fetch(ruta, cuerpo
    ? {method: 'POST', headers: {'Content-Type': 'application/json'},
       body: JSON.stringify(cuerpo)} : {});
  const datos = await r.json();
  if (!r.ok) throw new Error(datos.error || `error ${r.status}`);
  return datos;
}

let ESTADO = null;
let ACTIVIDAD_LISTA = false;

/* ------------------------------------------------------------------ hero */
function pintarHero(d) {
  const r = d.resumen, v = d.verificacion, s = d.sistema;
  $('#hero-pie').textContent =
    `De ${r.consultas} mensajes medidos, ${r.resueltas_sin_persona} se resolvieron sin ` +
    `intervenir. Catálogo de ${s.piezas_catalogo} piezas, todas con precio. ` +
    `Los mensajes están simulados; las decisiones y los tiempos son reales.`;

  const cifras = [
    [pct(r.tasa_resolucion), 'resueltas sin persona'],
    [`${r.ms_mediana} ms`, 'en responder'],
    [pct(v.tasa_acierto_verificado), 'acierto verificado'],
    [pct(r.tasa_ofertas_automaticas), 'ofertas cerradas solas'],
  ];
  $('#hero-cifras').replaceChildren(...cifras.map(([valor, que]) => {
    const caja = crear('div');
    caja.append(crear('p', 'valor', valor), crear('p', 'que', que));
    return caja;
  }));
}

/* ------------------------------------------------------------- ejemplos */
function pintarSugerencias(d) {
  const ejemplos = d.ejemplos || [];
  $('#sugerencias').replaceChildren(...ejemplos.map((texto) => {
    const b = crear('button', 'chip', texto);
    b.type = 'button';
    b.onclick = () => { $('#entrada').value = texto; consultar(texto); };
    return b;
  }));
}

/* ------------------------------------------------------------ evolución */
function pintarEvolucion(d) {
  const h = d.historico;
  if (!h) return;
  const cuerpo = $('#tabla-evolucion');
  if (!cuerpo) return;
  cuerpo.replaceChildren(...h.filas.map((fila) => {
    const [nombre, ...valores] = fila;
    const tr = crear('tr');
    const td = crear('td');
    td.append(nombre === 'TOTAL' ? crear('strong', null, nombre)
                                 : document.createTextNode(nombre));
    tr.append(td);
    const mejor = Math.max(...valores);
    valores.forEach((v) => {
      const celda = crear('td', 'num', pct(v));
      if (v === mejor && mejor > 0) celda.classList.add('mejor');
      else if (v === Math.min(...valores)) celda.classList.add('peor');
      tr.append(celda);
    });
    return tr;
  }));
}

/* -------------------------------------------------------------- diagrama */
function pintarDiagrama(d) {
  const r = d.resumen;
  const total = r.consultas, solo = r.resueltas_sin_persona, mesa = r.escaladas;
  // Muchos mensajes entran, el filtro los reparte en dos salidas. Una imagen
  // explica el producto entero mejor que tres párrafos.
  const svg = `
<svg class="diagrama" viewBox="0 0 720 260" role="img"
     aria-label="${total} mensajes entran; ${solo} los resuelve el bot y ${mesa} llegan a tu mesa">
  <defs>
    <marker id="p" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
      <path d="M0,0 L7,3.5 L0,7 z" fill="#63707f"/>
    </marker>
  </defs>
  ${[0, 1, 2, 3, 4].map((i) => `
    <circle cx="58" cy="${42 + i * 44}" r="13" fill="#10141c" stroke="#262e3a"/>
    <path d="M75 ${42 + i * 44} C 150 ${42 + i * 44}, 190 130, 268 130"
          fill="none" stroke="#262e3a" stroke-width="1.5" marker-end="url(#p)"/>`).join('')}
  <text x="58" y="248" text-anchor="middle" font-size="12">${total} mensajes</text>

  <rect x="276" y="98" width="150" height="64" rx="14" fill="#0b0e14" stroke="#29e0d2"/>
  <text x="351" y="124" text-anchor="middle" font-size="13" class="grande">VendIQ</text>
  <text x="351" y="143" text-anchor="middle" font-size="11">busca · decide · filtra</text>

  <path d="M430 118 C 500 118, 520 62, 588 62" fill="none" stroke="#29e0d2"
        stroke-width="1.8" marker-end="url(#p)"/>
  <path d="M430 142 C 500 142, 520 198, 588 198" fill="none" stroke="#ffb020"
        stroke-width="1.8" marker-end="url(#p)"/>

  <rect x="596" y="36" width="104" height="52" rx="12" fill="#0b0e14" stroke="#262e3a"/>
  <text x="648" y="58" text-anchor="middle" font-size="17" class="cifra" fill="#29e0d2">${solo}</text>
  <text x="648" y="76" text-anchor="middle" font-size="11">resueltos solos</text>

  <rect x="596" y="172" width="104" height="52" rx="12" fill="#0b0e14" stroke="#262e3a"/>
  <text x="648" y="194" text-anchor="middle" font-size="17" class="cifra" fill="#ffb020">${mesa}</text>
  <text x="648" y="212" text-anchor="middle" font-size="11">a tu mesa</text>
</svg>`;
  $('#diagrama').innerHTML = svg;
}

/* ------------------------------------------------------------------ KPIs */
function pintarKPIs(d) {
  const r = d.resumen, v = d.verificacion;
  const tiles = [
    ['Resueltas sin persona', pct(r.tasa_resolucion), '', `${r.escaladas} llegaron a tu mesa`, true],
    ['Tiempo de respuesta', r.ms_mediana, 'ms', `p95 ${r.ms_p95} ms`, true],
    ['Ofertas cerradas solas', pct(r.tasa_ofertas_automaticas), '',
     `${r.ofertas_por_regla} de ${r.ofertas} sin molestarte`, true],
    ['Acierto verificado', pct(v.tasa_acierto_verificado), '',
     `${v.correctas} de ${r.consultas} contrastadas`, true],
  ];
  $('#kpis').replaceChildren(...tiles.map(([et, cifra, unidad, nota, acento]) => {
    const caja = crear('div', 'ind' + (acento ? ' acento' : ''));
    caja.append(crear('p', 'etiqueta', et));
    const c = crear('p', 'cifra', String(cifra));
    if (unidad) c.append(crear('span', 'unidad', unidad));
    caja.append(c, crear('p', 'nota', nota));
    return caja;
  }));
}

/* ---------------------------------------------------------- verificación */
function pintarVerificacion(d) {
  const v = d.verificacion, total = d.resumen.consultas;
  const partes = [
    ['correcta', v.correctas, 'seg-ok', 'var(--cian)', '✓'],
    ['falso positivo', v.falsos_positivos, 'seg-falso', 'var(--rojo)', '✕'],
    ['sin respuesta', v.sin_respuesta, 'seg-nada', 'var(--ambar)', '!'],
  ].filter(([, n]) => n > 0);

  $('#seg-verif').replaceChildren(...partes.map(([nombre, n, clase]) => {
    const seg = crear('div', clase, n > total * 0.06 ? String(n) : '');
    seg.style.flex = String(n);
    seg.title = `${nombre}: ${n}`;
    return seg;
  }));
  $('#leyenda-verif').replaceChildren(...partes.map(([nombre, n, , color, icono]) => {
    const li = crear('span');
    const punto = crear('i');
    punto.style.background = color;
    li.append(punto, document.createTextNode(`${icono} ${nombre} — ${n}`));
    return li;
  }));
}

/* -------------------------------------------------------------- demanda */
function pintarDemanda(d) {
  const lista = d.demanda_no_cubierta || [];
  const max = Math.max(...lista.map((x) => x.veces), 1);
  $('#demanda').replaceChildren(...lista.map((x) => {
    const b = crear('div', 'barra');
    const fila = crear('div', 'fila');
    fila.append(crear('span', 'nombre', x.consulta),
                crear('span', 'valor', `${x.veces} ${x.veces === 1 ? 'vez' : 'veces'}`));
    const canal = crear('div', 'canal');
    const relleno = crear('div', 'relleno');
    relleno.style.width = `${(x.veces / max) * 100}%`;
    canal.append(relleno);
    b.append(fila, canal);
    return b;
  }));
}

/* -------------------------------------------------------------- consola */
function fichaHTML(r, rechazada) {
  const f = crear('div', 'ficha' + (rechazada ? ' rechazada' : ''));
  f.append(crear('div', 'score', r.puntuacion.toFixed(2)));
  const cuerpo = crear('div');
  cuerpo.append(crear('p', 'titulo', r.texto));
  const meta = crear('div', 'meta');
  if (r.id_pieza) meta.append(crear('span', '', `ID ${r.id_pieza}`));
  meta.append(crear('span', '', r.tipo));
  cuerpo.append(meta);

  // El precio se muestra aparte y siempre con su porqué: es la decisión que más
  // cuesta si se equivoca, así que nunca aparece un importe sin explicación.
  const pc = r.precio_cliente;
  if (pc && pc.estado !== 'no_aplica') {
    const caja = crear('div', 'precio-caja');
    if (pc.publicable) {
      caja.append(crear('span', 'importe', pc.importe));
    } else {
      caja.append(crear('span', 'bloqueado', 'sin precio para el cliente'));
    }
    caja.append(crear('span', 'razon', pc.motivo));
    cuerpo.append(caja);
  }
  f.append(cuerpo);
  return f;
}

function pintarConsulta(res) {
  const bloque = crear('div');
  const cab = crear('div', 'veredicto');
  const SELLOS = {
    'RESPONDE':      ['ok', '✓ RESPONDE'],
    'NO DISPONIBLE': ['escala', '⊘ NO LA TENGO'],
    'ESCALA':        ['escala', '! A TU MESA'],
  };
  const [clase, texto] = SELLOS[res.decision] || ['escala', res.decision];
  cab.append(crear('span', 'sello ' + clase, texto),
             crear('span', '', `«${res.pregunta}»`),
             crear('span', 'ms', `${res.ms} ms`));
  bloque.append(cab, crear('p', 'porque', res.porque));

  res.resultados.forEach((r) => bloque.append(fichaHTML(r, false)));
  if (res.descartados.length) {
    bloque.append(crear('p', 'descartadas-titulo',
      `Descartadas por no llegar al umbral (${res.descartados.length})`));
    res.descartados.forEach((r) => bloque.append(fichaHTML(r, true)));
  }
  $('#salida').replaceChildren(bloque);
}

async function consultar(texto) {
  const btn = $('#btn-consulta');
  btn.disabled = true;
  $('#salida').replaceChildren(crear('p', 'vacio', 'Buscando…'));
  try {
    pintarConsulta(await api('/api/consultar', {pregunta: texto}));
  } catch (e) {
    $('#salida').replaceChildren(crear('p', 'vacio', `No se pudo consultar: ${e.message}`));
  } finally {
    btn.disabled = false;
  }
}

/* -------------------------------------------------------------- precios */
async function cargarPrecios() {
  const {pendientes} = await api('/api/precios');

  // Con el catálogo actual (todas las piezas con precio) la cola sale vacía.
  // Se explica en vez de dejar un hueco: es un estado correcto, no un error.
  if (!pendientes.length) {
    $('#caja-precios').replaceChildren(Object.assign(crear('div', 'estado-vacio'), {
      innerHTML: '<strong>Ninguna pendiente.</strong> Todas las piezas del catálogo ' +
                 'tienen precio, así que el bot puede darlos todos.<br>' +
                 'Cuando entre una pieza recién desmontada y sin tasar, aparecerá aquí ' +
                 'ordenada por cuántas veces te la hayan pedido.',
    }));
    return;
  }

  $('#tabla-precios').replaceChildren(...pendientes.map((p) => {
    const tr = crear('tr');
    tr.append(crear('td', '', p.descripcion), crear('td', '', p.disponibilidad));
    tr.append(crear('td', 'num', String(p.veces_preguntada)));

    const td = crear('td');
    if (p.precio_fijado) {
      const ok = crear('span', 'pastilla p-ok', p.precio_fijado);
      td.append(ok);
    } else {
      const caja = crear('div', 'precio-inline');
      const inp = crear('input');
      inp.type = 'number'; inp.step = '0.01'; inp.min = '0'; inp.placeholder = '€';
      inp.setAttribute('aria-label', `Precio para ${p.descripcion}`);
      const bt = crear('button', 'boton mini', 'Guardar');
      bt.onclick = async () => {
        const importe = parseFloat(inp.value);
        if (!(importe > 0)) return;
        try {
          await api('/api/precio', {id_pieza: p.id, importe});
          await cargarPrecios();
        } catch (e) { alert(`No se pudo guardar: ${e.message}`); }
      };
      inp.onkeydown = (e) => { if (e.key === 'Enter') bt.click(); };
      caja.append(inp, bt);
      td.append(caja);
    }
    tr.append(td);
    return tr;
  }));
}

/* -------------------------------------------------------------- ofertas */
const CLASE_DECISION = {ACEPTAR: 'p-ok', CONTRAOFERTA: 'p-ambar',
                        RECHAZAR: 'p-rojo', A_MANO: 'p-gris'};

async function cargarOfertas() {
  const {ofertas, piezas} = await api('/api/ofertas');
  const sel = $('#sel-pieza');
  if (!sel.options.length) {
    sel.replaceChildren(...piezas.map((p) => {
      const o = crear('option', null, `${p.descripcion} — ${eur(p.precio)} · ${p.antiguedad}`);
      o.value = p.id; o.dataset.precio = p.precio;
      return o;
    }));
    sel.dispatchEvent(new Event('change'));
  }

  $('#tabla-ofertas').replaceChildren(...[...ofertas].reverse().map((o) => {
    const tr = crear('tr');
    tr.append(crear('td', 'num', String(o.n)), crear('td', '', o.descripcion),
              crear('td', '', o.cliente),
              crear('td', 'num', o.precio_lista ? eur(o.precio_lista) : '—'),
              crear('td', 'num', eur(o.importe)),
              crear('td', 'num', o.descuento != null ? pct(o.descuento) : '—'),
              crear('td', '', o.antiguedad || '—'));

    const tdDec = crear('td');
    const p = crear('span', 'pastilla ' + (CLASE_DECISION[o.decision] || 'p-gris'), o.decision);
    p.title = o.motivo || '';
    tdDec.append(p);
    tr.append(tdDec);

    const tdAcc = crear('td');
    if (o.estado === 'pendiente') {
      const si = crear('button', 'boton mini', 'Aceptar');
      const no = crear('button', 'boton mini peligro', 'Rechazar');
      si.onclick = () => resolver(o.n, 'ACEPTAR');
      no.onclick = () => resolver(o.n, 'RECHAZAR');
      tdAcc.append(si, document.createTextNode(' '), no);
    } else {
      tdAcc.append(crear('span', 'pastilla p-gris', o.resuelta_por || 'regla'));
    }
    tr.append(tdAcc);
    return tr;
  }));
}

async function resolver(n, decision) {
  try {
    await api('/api/resolver', {n, decision, motivo: 'decidido desde el panel'});
    await cargarOfertas();
  } catch (e) { alert(`No se pudo resolver: ${e.message}`); }
}

/* ------------------------------------------------------------- registro */
let FILTRO = 'todas';
const VEREDICTOS = {
  correcta: ['✓ correcta', 'p-ok'],
  falso_positivo: ['✕ falso positivo', 'p-rojo'],
  sin_respuesta: ['! sin respuesta', 'p-ambar'],
  pieza_equivocada: ['✕ pieza equivocada', 'p-rojo'],
};

function pintarRegistro() {
  const filas = (ESTADO.consultas || []).filter((c) =>
    FILTRO === 'todas' ||
    (FILTRO === 'resueltas' && c.decision === 'RESUELTA') ||
    (FILTRO === 'escaladas' && c.decision === 'ESCALADA') ||
    (FILTRO === 'fallos' && c.veredicto !== 'correcta'));

  $('#tabla-registro').replaceChildren(...filas.map((c) => {
    const tr = crear('tr');
    tr.append(crear('td', 'num', c.hora.slice(11)), crear('td', '', c.mensaje));
    const td1 = crear('td');
    td1.append(crear('span', 'pastilla ' + (c.decision === 'RESUELTA' ? 'p-ok' : 'p-ambar'),
                     c.decision));
    const [texto, clase] = VEREDICTOS[c.veredicto] || [c.veredicto, 'p-gris'];
    const td2 = crear('td');
    const p = crear('span', 'pastilla ' + clase, texto);
    p.title = c.porque;
    td2.append(p);
    tr.append(td1, td2, crear('td', 'num', String(c.ms)));
    return tr;
  }));
}

function pintarFiltros() {
  const opciones = [['todas', 'Todas'], ['resueltas', 'Resueltas'],
                    ['escaladas', 'A tu mesa'], ['fallos', 'Solo fallos']];
  $('#filtros').replaceChildren(...opciones.map(([clave, etiqueta]) => {
    const b = crear('button', 'chip', etiqueta);
    b.setAttribute('aria-pressed', String(clave === FILTRO));
    b.onclick = () => { FILTRO = clave; pintarFiltros(); pintarRegistro(); };
    return b;
  }));
}

/* ---------------------------------------------------------------- motor */
function pintarMotor(d) {
  const s = d.sistema, q = d.calidad_medida;
  const tiles = [
    ['Fichas indexadas', s.fichas_indexadas, `${s.dimensiones} dimensiones cada una`],
    ['Peso léxico / significado', `${s.peso_lexico} · ${s.peso_semantico}`,
     'una sola fórmula para ordenar'],
    ['Mínimo para ofrecer pieza', s.umbral_pieza, 'por debajo, no se ofrece nada'],
    ['Mínimo para dar precio', s.umbral_precio ?? '—',
     'más alto: un precio erróneo cuesta dinero'],
    ['Vocabulario aprendido', `${s.marcas} marcas · ${s.tipos_pieza} tipos`,
     'sale del catálogo, no de una lista escrita'],
    ['Acierto en banco de pruebas', pct(q.acierto_ahora),
     `antes ${pct(q.acierto_antes)} · ${q.preguntas_banco} preguntas`],
  ];
  $('#motor').replaceChildren(...tiles.map(([et, cifra, nota]) => {
    const caja = crear('div', 'ind');
    caja.append(crear('p', 'etiqueta', et), crear('p', 'cifra', String(cifra)),
                crear('p', 'nota', nota));
    return caja;
  }));
}

/* ----------------------------------------------------------------- init */
async function iniciar() {
  try {
    ESTADO = await api('/api/estado');
  } catch {
    $('#estado-texto').textContent = 'sin conexión';
    $('#hero-pie').textContent = 'Arranca el panel con:  python 06_panel.py';
    return;
  }
  const s = ESTADO.sistema;
  $('#estado-texto').textContent = `${s.piezas_catalogo} piezas · índice cargado`;
  $('#pie-nota').innerHTML =
    `Datos generados por <code>05_panel_datos.py</code> y servidos por <code>06_panel.py</code>. ` +
    `El acierto sale de <code>${ESTADO.calidad_medida.fuente}</code>. ` +
    `Última generación: ${ESTADO.generado.replace('T', ' ').replace('+00:00', ' UTC')}.`;

  pintarSugerencias(ESTADO);
  pintarEvolucion(ESTADO);
  // El hero, el diagrama y los KPIs los pinta actividad.js con los datos
  // medidos de 10_simular.py, que son miles de mensajes en vez de treinta.
  // Si esos datos no existen todavía, actividad.js llama a estas de aquí.
  if (!ACTIVIDAD_LISTA) { pintarHero(ESTADO); pintarDiagrama(ESTADO); pintarKPIs(ESTADO); }
  pintarVerificacion(ESTADO);
  pintarDemanda(ESTADO);
  pintarFiltros();
  pintarRegistro();
  pintarMotor(ESTADO);
  await Promise.all([cargarOfertas(), cargarPrecios()]);
}

$('#form-consulta').addEventListener('submit', (e) => {
  e.preventDefault();
  const texto = $('#entrada').value.trim();
  if (texto) consultar(texto);
});
$('#sel-pieza').addEventListener('change', (e) => {
  const precio = parseFloat(e.target.selectedOptions[0]?.dataset.precio || '0');
  $('#inp-importe').value = (precio * 0.88).toFixed(2);
});
$('#btn-oferta').addEventListener('click', async () => {
  const id = $('#sel-pieza').value, importe = parseFloat($('#inp-importe').value);
  if (!id || !(importe > 0)) return;
  try {
    await api('/api/oferta', {id_pieza: id, importe, cliente: $('#inp-cliente').value});
    await cargarOfertas();
  } catch (e) { alert(`No se pudo registrar: ${e.message}`); }
});

iniciar();
