/* VendIQ · Centro de control
   Todo lo que se pinta aquí viene del servidor, que a su vez lo saca de ejecutar el
   buscador y el motor de ofertas reales. No hay ni un dato escrito a mano. */

const $ = (sel) => document.querySelector(sel);
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
  const opciones = cuerpo
    ? {method: 'POST', headers: {'Content-Type': 'application/json'},
       body: JSON.stringify(cuerpo)}
    : {};
  const r = await fetch(ruta, opciones);
  const datos = await r.json();
  if (!r.ok) throw new Error(datos.error || `error ${r.status}`);
  return datos;
}

let ESTADO = null;

/* ------------------------------------------------------------------ KPIs */
function pintarKPIs(d) {
  const r = d.resumen, v = d.verificacion;
  const tiles = [
    ['Consultas atendidas', r.consultas, '', `en la ventana medida`, false],
    ['Resueltas sin persona', pct(r.tasa_resolucion), '',
     `${r.escaladas} pasaron a una persona`, true],
    ['Respuesta', r.ms_mediana, 'ms', `p95 ${r.ms_p95} ms`, true],
    ['Ofertas por regla', pct(r.tasa_ofertas_automaticas), '',
     `${r.ofertas_por_regla} de ${r.ofertas} sin molestar a nadie`, true],
    ['Acierto verificado', pct(v.tasa_acierto_verificado), '',
     `${v.correctas} de ${r.consultas} contrastadas`, true],
  ];
  const cont = $('#kpis');
  cont.replaceChildren(...tiles.map(([et, cifra, unidad, nota, destaca]) => {
    const caja = crear('div', 'ind' + (destaca ? ' destaca' : ''));
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

  // Identidad nunca por color solo: icono + etiqueta + número.
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
function pintarConsulta(res) {
  const salida = $('#salida');
  const bloque = crear('div');

  const cab = crear('div', 'veredicto');
  const SELLOS = {
    'RESPONDE':      ['ok', '✓ RESPONDE'],
    'NO DISPONIBLE': ['escala', '⊘ NO LA TENGO'],
    'ESCALA':        ['escala', '! ESCALA'],
  };
  const [claseSello, textoSello] = SELLOS[res.decision] || ['escala', res.decision];
  cab.append(crear('span', 'sello ' + claseSello, textoSello));
  cab.append(crear('span', '', `«${res.pregunta}»`));
  cab.append(crear('span', 'ms', `${res.ms} ms`));
  bloque.append(cab, crear('p', 'porque', res.porque));

  const ficha = (r, rechazada) => {
    const f = crear('div', 'ficha' + (rechazada ? ' rechazada' : ''));
    f.append(crear('div', 'score', r.puntuacion.toFixed(2)));
    const cuerpo = crear('div', 'cuerpo');
    cuerpo.append(crear('p', 'titulo', r.texto));
    const meta = crear('div', 'meta');
    meta.append(crear('span', 'tipo', r.tipo));
    if (r.precio) meta.append(crear('span', '', r.precio));
    if (r.id_pieza) meta.append(crear('span', '', `ID ${r.id_pieza}`));
    cuerpo.append(meta);
    f.append(cuerpo);
    return f;
  };

  if (res.resultados.length) {
    res.resultados.forEach((r) => bloque.append(ficha(r, false)));
  }
  if (res.descartados.length) {
    bloque.append(crear('p', 'descartadas-titulo',
      `Descartadas por no llegar al umbral (${res.descartados.length})`));
    res.descartados.forEach((r) => bloque.append(ficha(r, true)));
  }

  salida.replaceChildren(bloque);
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

/* -------------------------------------------------------------- ofertas */
const CLASE_DECISION = {
  ACEPTAR: 'p-ok', CONTRAOFERTA: 'p-ambar', RECHAZAR: 'p-rojo', A_MANO: 'p-gris',
};

async function cargarOfertas() {
  const {ofertas, piezas} = await api('/api/ofertas');

  const sel = $('#sel-pieza');
  if (!sel.options.length) {
    sel.replaceChildren(...piezas.map((p) => {
      const o = crear('option', null,
        `${p.descripcion} — ${eur(p.precio)} · ${p.antiguedad}`);
      o.value = p.id;
      o.dataset.precio = p.precio;
      return o;
    }));
    sel.dispatchEvent(new Event('change'));
  }

  $('#tabla-ofertas').replaceChildren(...[...ofertas].reverse().map((o) => {
    const tr = crear('tr');
    const celda = (txt, clase) => crear('td', clase, txt);
    tr.append(celda(String(o.n), 'num'), celda(o.descripcion), celda(o.cliente));
    tr.append(celda(o.precio_lista ? eur(o.precio_lista) : '—', 'num'));
    tr.append(celda(eur(o.importe), 'num'));
    tr.append(celda(o.descuento != null ? pct(o.descuento) : '—', 'num'));
    tr.append(celda(o.antiguedad || '—'));

    const tdDec = crear('td');
    const p = crear('span', 'pastilla ' + (CLASE_DECISION[o.decision] || 'p-gris'),
                    o.decision);
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
  } catch (e) {
    alert(`No se pudo resolver: ${e.message}`);
  }
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
  const todas = ESTADO.consultas || [];
  const filas = todas.filter((c) =>
    FILTRO === 'todas' ||
    (FILTRO === 'resueltas' && c.decision === 'RESUELTA') ||
    (FILTRO === 'escaladas' && c.decision === 'ESCALADA') ||
    (FILTRO === 'fallos' && c.veredicto !== 'correcta'));

  $('#tabla-registro').replaceChildren(...filas.map((c) => {
    const tr = crear('tr');
    tr.append(crear('td', 'num', c.hora.slice(11)));
    tr.append(crear('td', '', c.mensaje));

    const td1 = crear('td');
    td1.append(crear('span', 'pastilla ' +
      (c.decision === 'RESUELTA' ? 'p-ok' : 'p-ambar'), c.decision));
    tr.append(td1);

    const [texto, clase] = VEREDICTOS[c.veredicto] || [c.veredicto, 'p-gris'];
    const td2 = crear('td');
    const p = crear('span', 'pastilla ' + clase, texto);
    p.title = c.porque;
    td2.append(p);
    tr.append(td2, crear('td', 'num', String(c.ms)));
    return tr;
  }));
}

function pintarFiltros() {
  const opciones = [['todas', 'Todas'], ['resueltas', 'Resueltas'],
                    ['escaladas', 'Escaladas'], ['fallos', 'Solo fallos']];
  $('#filtros').replaceChildren(...opciones.map(([clave, etiqueta]) => {
    const b = crear('button', 'chip', etiqueta);
    if (clave === FILTRO) b.style.borderColor = 'var(--cian)';
    b.onclick = () => { FILTRO = clave; pintarFiltros(); pintarRegistro(); };
    return b;
  }));
}

/* ---------------------------------------------------------------- motor */
function pintarMotor(d) {
  const s = d.sistema, q = d.calidad_medida;
  const tiles = [
    ['Fichas indexadas', s.fichas_indexadas, `${s.dimensiones} dimensiones por ficha`],
    ['Peso léxico / semántico', `${s.peso_lexico} · ${s.peso_semantico}`,
     'una sola fórmula para ordenar'],
    ['Umbral pieza', s.umbral_pieza, 'por debajo, no se ofrece nada'],
    ['Umbral política', s.umbral_politica, 'las condiciones se preguntan con otras palabras'],
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
  } catch (e) {
    $('#estado-texto').textContent = 'sin conexión con el servidor';
    $('#aviso').textContent = 'Arranca el panel con:  python 06_panel.py';
    return;
  }

  const s = ESTADO.sistema;
  $('#estado-texto').textContent =
    `${s.fichas_indexadas} fichas · ${s.piezas_catalogo} piezas · índice cargado`;
  $('#aviso').innerHTML = `<b>Prototipo.</b> ${ESTADO.aviso}`;
  $('#pie-nota').innerHTML =
    `Datos generados por <code>05_panel_datos.py</code> y servidos por <code>06_panel.py</code>. ` +
    `El acierto del banco de pruebas sale de <code>${ESTADO.calidad_medida.fuente}</code>. ` +
    `Última generación: ${ESTADO.generado.replace('T', ' ').replace('+00:00', ' UTC')}.`;

  pintarKPIs(ESTADO);
  pintarVerificacion(ESTADO);
  pintarDemanda(ESTADO);
  pintarFiltros();
  pintarRegistro();
  pintarMotor(ESTADO);
  await cargarOfertas();
}

$('#form-consulta').addEventListener('submit', (e) => {
  e.preventDefault();
  const texto = $('#entrada').value.trim();
  if (texto) consultar(texto);
});

document.querySelectorAll('.sugerencias .chip').forEach((chip) => {
  chip.onclick = () => { $('#entrada').value = chip.textContent; consultar(chip.textContent); };
});

$('#sel-pieza').addEventListener('change', (e) => {
  const precio = parseFloat(e.target.selectedOptions[0]?.dataset.precio || '0');
  $('#inp-importe').value = (precio * 0.88).toFixed(2);   // una oferta plausible
});

$('#btn-oferta').addEventListener('click', async () => {
  const id = $('#sel-pieza').value;
  const importe = parseFloat($('#inp-importe').value);
  if (!id || !(importe > 0)) return;
  try {
    await api('/api/oferta', {id_pieza: id, importe, cliente: $('#inp-cliente').value});
    await cargarOfertas();
  } catch (e) {
    alert(`No se pudo registrar: ${e.message}`);
  }
});

iniciar();
