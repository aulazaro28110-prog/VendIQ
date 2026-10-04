/* VendIQ · simulador de conversación de WhatsApp
   ------------------------------------------------------------------------
   El chat NO tiene lógica de negocio. Manda el mensaje al servidor y pinta lo
   que le devuelve: el texto, la traza del «por qué» y lo que el bot recuerda.
   La memoria de la conversación vive en Python, no aquí — si viviera en el
   navegador, recargar la página cambiaría lo que responde el bot, y entonces
   esto sería una maqueta y no una prueba.

   El «por qué» se pinta a partir de `datos.traza` (Fase 4), que viene del
   servidor paso a paso. Si una respuesta no la trae (servidor viejo), se cae al
   «por qué» de siempre sin romperse. La evaluación ✓/✗ de los guiones también la
   hace el servidor (misma definición que el banco): aquí solo se pinta. */

const SESION = `panel-${Date.now()}`;
// La sesión del chat escrito a mano es `panel-…` y SÍ escribe reservas a
// propósito (es el cliente de prueba de Álvaro). Los guiones, en cambio, corren
// en una sesión `guion-<id>-<marca de tiempo>` que `es_prueba` excluye, para que
// reproducirlos no deje rastro en los datos del negocio (C6, §6.2).
let SESION_ACTIVA = SESION;
let PERFIL = 'nuevo';
let OCUPADO = false;
let PRIMERO = true;          // el próximo mensaje reinicia la conversación
let VEL = 'normal';          // velocidad del reproductor de guiones

// Lo que ha devuelto el servidor en cada turno del bot, para poder volver a
// pintar el «por qué» de un turno anterior al hacer clic en su burbuja.
const TURNOS = [];
// Marcador del guion en curso (✓/✗ por turno y resumen final).
const REPRO = {activo: false, parar: false, guion: null, i: 0, modo: null};
let OK_GUION = 0, TURNOS_GUION = 0, INV_GUION = 0;

const hora = () => new Date().toLocaleTimeString('es-ES',
  {hour: '2-digit', minute: '2-digit'});

// Las pausas de animación se encogen en modo «Rápida», no se quitan (§9.1).
const pausa = (ms) => new Promise((r) => setTimeout(r, ms * (VEL === 'rapida' ? 0.4 : 1)));

/* ------------------------------------------------------------- burbujas */
function burbuja(texto, quien, seguida) {
  const b = crear('div', `burbuja ${quien}${seguida ? ' seguida' : ''}`);
  b.append(document.createTextNode(texto));
  const t = crear('span', 'hora', hora());
  if (quien === 'enviada') t.append(crear('span', 'visto', '✓✓'));
  b.append(t);
  $('#hilo').append(b);
  $('#hilo').scrollTop = $('#hilo').scrollHeight;
  return b;
}

function escribiendo(encender) {
  const previo = $('#puntitos');
  if (previo) previo.remove();
  $('#chat-subtitulo').textContent = encender ? 'escribiendo…' : 'en línea';
  if (!encender) return;
  const caja = crear('div', 'escribiendo');
  caja.id = 'puntitos';
  caja.append(crear('i'), crear('i'), crear('i'));
  $('#hilo').append(caja);
  $('#hilo').scrollTop = $('#hilo').scrollHeight;
}

/* Botones de aclaración. Las opciones vienen del servidor y salen de piezas
   reales del catálogo: aquí no se genera ninguna. Al pulsar se manda el mismo
   texto que habría escrito el cliente, así el botón entra por la misma puerta
   que el texto libre y no abre un camino con reglas propias. */
function pintarBotones(opciones) {
  if (!opciones) return;
  const caja = crear('div', 'botones-aclara');
  caja.id = 'botones-aclara';
  opciones.opciones.forEach((o) => {
    const b = crear('button', 'boton-aclara', o.texto);
    b.type = 'button';
    b.onclick = () => { caja.remove(); enviar(o.envia); };
    caja.append(b);
  });
  $('#hilo').append(caja);
  $('#hilo').scrollTop = $('#hilo').scrollHeight;
}

function limpiarHilo() {
  $('#hilo').replaceChildren(crear('div', 'dia', 'HOY'));
  $('#porque-caja').replaceChildren(
    crear('p', 'vacio', 'Manda un mensaje o elige una conversación tipo.'));
  TURNOS.length = 0;
  OK_GUION = TURNOS_GUION = INV_GUION = 0;
  SESION_ACTIVA = SESION;        // volver al chat a mano (los guiones la cambian)
  PRIMERO = true;
}

/* -------------------------------------------------------- el «por qué» */
const SELLOS = {
  'RESPONDE':      ['ok', '✓ RESUELVE'],
  'NO DISPONIBLE': ['escala', '⊘ NO LA TENGO'],
  'ESCALA':        ['escala', '! A TU MESA'],
};
const ACCIONES = {RESPONDER: 'ok', PREGUNTAR: 'escala', ESCALAR: 'escala'};
const NUM = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨'];

function pasoDe(traza, nombre) {
  return (traza.pasos || []).find((p) => p.paso === nombre) || null;
}

// Cabecera común (acción, sello de decisión, intención, ms) y, si el turno viene
// de un guion, el veredicto esperado/obtenido. Se usa en las dos vistas.
function cabecera(datos) {
  const {bot, busqueda} = datos;
  const cab = crear('div', 'porque-cab');
  cab.append(crear('span', 'sello ' + (ACCIONES[bot.accion] || 'escala'),
                   bot.accion || busqueda.decision));
  const [clase, texto] = SELLOS[busqueda.decision] || ['escala', busqueda.decision];
  cab.append(crear('span', 'pastilla ' + (clase === 'ok' ? 'p-ok' : 'p-ambar'), texto));
  if (bot.intencion) cab.append(crear('span', 'pastilla p-gris', bot.intencion));
  if (busqueda.ms != null) cab.append(crear('span', 'ms', `${busqueda.ms} ms`));
  return cab;
}

// El precio, siempre con su motivo. Si alguna vez se publicara uno que el
// buscador no autorizó, sale en rojo: es el fallo que no puede pasar. Es el
// guardarraíl, así que va arriba del todo y no escondido en un paso (§9.3).
function selloPrecio(datos) {
  const {bot, busqueda} = datos;
  const piezas = (busqueda.resultados || []).filter((r) => r.tipo === 'inventario');
  const pc = piezas.length ? piezas[0].precio_cliente : null;
  if (!pc || pc.estado === 'no_aplica') return null;
  const s = crear('div', 'sello-precio' + (bot.precio_autorizado ? '' : ' fuga'));
  s.append(pc.publicable ? crear('span', 'importe', pc.importe)
                         : crear('span', 'bloqueado', 'PRECIO RETENIDO'));
  s.append(crear('span', 'razon', bot.precio_autorizado ? pc.motivo
    : '¡FUGA! se ha publicado un importe que la búsqueda no autorizó'));
  return s;
}

// Una fila-paso plegable: resumen (icono de estado + número + título + una
// línea) y, al abrir, los datos. Los pasos sin contenido se pintan en gris con
// «—», no se esconden: así se ve que el paso se evaluó (§9.3).
function filaPaso(n, estado, titulo, linea, cuerpo) {
  const d = crear('details', 'paso');
  const s = crear('summary', 'paso-sum');
  s.append(crear('span', 'paso-ico e-' + (estado || 'info')));
  s.append(crear('span', 'paso-num', NUM[n]));
  s.append(crear('span', 'paso-tit', titulo));
  s.append(crear('span', 'paso-linea' + (linea === '—' ? ' vacia' : ''),
                 linea == null ? '—' : linea));
  d.append(s);
  if (cuerpo) d.append(cuerpo);
  return d;
}

function barraBusqueda(mejor) {
  if (!mejor || mejor.puntuacion == null) return null;
  const score = Math.max(0, Math.min(1, mejor.puntuacion));
  const umbral = Math.max(0, Math.min(1, mejor.umbral || 0));
  const llega = mejor.puntuacion >= (mejor.umbral || 0);
  const caja = crear('div', 'barra-caja');
  const barra = crear('div', 'barra');
  const llena = crear('span', 'barra-llena' + (llega ? '' : ' corta'));
  llena.style.width = (score * 100).toFixed(0) + '%';
  const marca = crear('span', 'barra-umbral');
  marca.style.left = (umbral * 100).toFixed(0) + '%';
  barra.append(llena, marca);
  caja.append(barra);
  const txt = `${mejor.puntuacion.toFixed(2)} ${llega ? '≥' : '<'} umbral ${(mejor.umbral || 0).toFixed(2)}`;
  caja.append(crear('span', 'barra-txt', txt));
  return caja;
}

function listaDatos(pares) {
  const dl = crear('div', 'paso-datos');
  pares.filter(([, v]) => v !== null && v !== undefined && v !== '')
    .forEach(([k, v]) => {
      const row = crear('div', 'pd');
      row.append(crear('span', 'pd-k', k), crear('span', 'pd-v', String(v)));
      dl.append(row);
    });
  return dl.children.length ? dl : null;
}

// Las auditorías del texto: una píldora por guarda (verde/roja). Solo hay cuando
// redacta el LLM; sin LLM la lista va vacía y se dice.
function pildorasAuditoria(auditorias) {
  const caja = crear('div', 'audit-pills');
  if (!auditorias || !auditorias.length) {
    caja.append(crear('span', 'audit-nota', 'sin LLM: lo escribió el redactor determinista'));
    return caja;
  }
  auditorias.forEach((a) => {
    const p = crear('span', 'pill-audit ' + (a.ok ? 'ok' : 'no'),
                    (a.ok ? '✓ ' : '✗ ') + a.nombre);
    if (!a.ok && a.motivo) p.title = a.motivo;
    caja.append(p);
  });
  return caja;
}

function pintarTraza(datos) {
  const traza = datos.traza;
  const caja = crear('div');

  caja.append(cabecera(datos));
  if (datos.evaluacion && !datos.evaluacion.error) {
    const ev = datos.evaluacion;
    const v = crear('p', 'porque-veredicto ' + (ev.ok ? 'ok' : 'no'));
    v.textContent = `${ev.ok ? '✓' : '✗'} esperado: ${ev.esperado} · obtenido: ${ev.obtenido}`;
    caja.append(v);
  }
  // El resumen, en grande: es lo primero que se lee (§9.3).
  if (traza.resumen) caja.append(crear('p', 'resumen-grande', traza.resumen));

  const sp = selloPrecio(datos);
  if (sp) caja.append(sp);

  // ---- los 8 pasos --------------------------------------------------------
  const pasos = crear('div', 'pasos');

  const e = pasoDe(traza, 'entrada') || {};
  const ed = e.datos || {};
  pasos.append(filaPaso(0, 'info', 'Qué ha leído',
    [ed.intencion ? `intención: ${ed.intencion}` : null,
     ed.habla_de_pieza ? 'nombra una pieza' : 'sin pieza',
     ed.coche_en_mensaje ? `coche: ${ed.coche_en_mensaje}` : 'sin coche',
     ed.matricula_en_mensaje ? 'con matrícula' : null].filter(Boolean).join(' · '),
    listaDatos([['intención', ed.intencion], ['habla de pieza', ed.habla_de_pieza],
                ['coche en el mensaje', ed.coche_en_mensaje],
                ['matrícula en el mensaje', ed.matricula_en_mensaje]])));

  const ctx = pasoDe(traza, 'contexto') || {};
  const esNinguna = (ctx.rama || 'ninguna') === 'ninguna';
  pasos.append(filaPaso(1, 'info', 'Memoria usada',
    esNinguna ? '— (no ha hecho falta)' : (ctx.por_que || ctx.rama),
    esNinguna ? null : listaDatos([['rama', ctx.rama],
                                   ['texto buscado', ctx.texto_buscado]])));

  const bus = pasoDe(traza, 'busqueda') || {};
  const mejor = bus.mejor;
  const barra = barraBusqueda(mejor);
  const cuerpoBus = crear('div', 'paso-cuerpo');
  if (barra) cuerpoBus.append(barra);
  const ld = listaDatos([['decisión', bus.decision], ['candidatos', bus.candidatos],
                         ['ms', bus.ms]]);
  if (ld) cuerpoBus.append(ld);
  pasos.append(filaPaso(2, bus.estado || 'info', 'Qué ha encontrado',
    mejor ? `${mejor.titulo}` : 'nada por encima del umbral',
    cuerpoBus.children.length ? cuerpoBus : null));

  const pr = pasoDe(traza, 'precio') || {};
  const lineaPr = pr.publicable === null || pr.publicable === undefined
    ? 'no aplica'
    : (pr.publicable ? 'publicable' : 'retenido') + (pr.motivo ? ` — ${pr.motivo}` : '');
  pasos.append(filaPaso(3,
    pr.estado === 'no_aplica' ? 'gris' : (pr.estado || 'info'), 'Precio',
    lineaPr,
    listaDatos([['publicable', pr.publicable], ['motivo', pr.motivo],
                ['coche identificado', pr.coche_identificado],
                ['umbral de precio', pr.umbral_precio]])));

  const rg = pasoDe(traza, 'reglas') || {};
  const reglas = rg.reglas || [];
  const cuerpoReg = crear('div', 'paso-cuerpo');
  reglas.forEach((r) => {
    const b = crear('div', 'regla' +
      (/escalad|queja|no se reconoce/.test(r.regla) ? ' aviso' : ''));
    b.append(crear('p', 'que', r.regla), crear('p', 'detalle', r.detalle || ''));
    cuerpoReg.append(b);
  });
  pasos.append(filaPaso(4, 'info', 'Reglas del redactor',
    reglas.length ? reglas.map((r) => r.regla).join(' · ') : '—',
    cuerpoReg.children.length ? cuerpoReg : null));

  const ac = pasoDe(traza, 'accion') || {};
  pasos.append(filaPaso(5, ac.estado || 'ok', 'Decisión',
    `${ac.accion || ''} — ${ac.por_que || ''}`.trim(),
    null));

  const re = pasoDe(traza, 'redaccion') || {};
  const cuerpoRed = crear('div', 'paso-cuerpo');
  cuerpoRed.append(pildorasAuditoria(re.auditorias));
  if (re.nota) cuerpoRed.append(crear('p', 'audit-nota', re.nota));
  // Si se descartó al modelo, se puede ver lo que escribió al lado de lo enviado.
  if (re.texto_modelo) {
    const det = crear('details', 'diff');
    det.append(crear('summary', 'diff-sum', 'ver lo que escribió el modelo'));
    const cols = crear('div', 'diff-cols');
    const c1 = crear('div', 'diff-col malo');
    c1.append(crear('p', 'diff-et', 'escribió el modelo (descartado)'),
              crear('p', 'diff-txt', re.texto_modelo));
    const c2 = crear('div', 'diff-col');
    c2.append(crear('p', 'diff-et', 'se envió'),
              crear('p', 'diff-txt', re.texto_enviado || ''));
    cols.append(c1, c2);
    det.append(cols);
    cuerpoRed.append(det);
  }
  pasos.append(filaPaso(6, re.estado || 'ok', 'Quién lo escribe',
    re.redactor || 'determinista', cuerpoRed));

  const mem = pasoDe(traza, 'memoria') || {};
  const antes = mem.antes || {}, despues = mem.despues || {}, cambios = mem.cambios || [];
  const cuerpoMem = crear('div', 'paso-cuerpo');
  Object.keys(despues).forEach((k) => {
    const v = despues[k];
    if (v === null || v === undefined || v === '') return;
    const row = crear('div', 'pd' + (cambios.includes(k) ? ' pd-nuevo' : ''));
    row.append(crear('span', 'pd-k', k));
    const val = cambios.includes(k) && antes[k]
      ? `${antes[k] ?? '—'} → ${v}` : String(v);
    row.append(crear('span', 'pd-v', val));
    cuerpoMem.append(row);
  });
  pasos.append(filaPaso(7, 'info', 'Qué recuerda ahora',
    cambios.length ? `cambia: ${cambios.join(', ')}` : 'sin cambios',
    cuerpoMem.children.length ? cuerpoMem : null));

  caja.append(pasos);

  // Descartadas: plegadas, solo las del mismo tipo que la decisión (§9.3).
  const decTipo = mejor ? mejor.tipo : null;
  const descart = (datos.busqueda.descartados || [])
    .filter((r) => !decTipo || r.tipo === decTipo);
  if (descart.length) {
    const det = crear('details', 'descartadas');
    det.append(crear('summary', 'porque-sub',
      `Descartadas por no llegar al umbral (${descart.length})`));
    descart.slice(0, 3).forEach((r) => det.append(fichaHTML(r, true)));
    caja.append(det);
  }

  return caja;
}

/* El «por qué» de siempre, por si una respuesta no trae traza (servidor viejo). */
function pintarPorqueViejo(datos) {
  const {bot, busqueda, memoria} = datos;
  const caja = crear('div');
  caja.append(cabecera(datos));
  if (bot.porque_accion) caja.append(crear('p', 'porque', bot.porque_accion));
  if (bot.redactor) {
    const r = crear('p', 'quien-redacta' + (bot.llm_descartado ? ' malo' : ''));
    r.textContent = '✎ ' + bot.redactor;
    caja.append(r);
  }
  const mem = crear('div', 'memoria');
  [['turno', memoria.turnos],
   ['trato', memoria.perfil === 'conocido'
      ? `${memoria.nombre || 'conocido'}, de confianza` : 'nuevo'],
   ['matrícula', memoria.matricula], ['coche', memoria.vehiculo],
   ['pieza sobre la mesa', memoria.pieza],
   ['en manos de Álvaro', memoria.escalado ? 'sí' : null]]
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .forEach(([k, v]) => {
      const d = crear('span', 'dato');
      d.append(document.createTextNode(`${k}: `), crear('b', null, String(v)));
      mem.append(d);
    });
  caja.append(mem);
  const sp = selloPrecio(datos);
  if (sp) caja.append(sp);
  caja.append(crear('p', 'porque-sub', 'Reglas aplicadas'));
  (bot.reglas || []).forEach((r) => {
    const b = crear('div', 'regla' +
      (/escalad|queja|no se reconoce/.test(r.regla) ? ' aviso' : ''));
    b.append(crear('p', 'que', r.regla), crear('p', 'detalle', r.detalle || ''));
    caja.append(b);
  });
  const piezas = (busqueda.resultados || []).filter((r) => r.tipo === 'inventario');
  if (piezas.length) {
    caja.append(crear('p', 'porque-sub', 'Fichas recuperadas'));
    piezas.forEach((r) => caja.append(fichaHTML(r, false)));
  }
  return caja;
}

function pintarPorque(datos) {
  const caja = (datos && datos.traza && (datos.traza.pasos || []).length)
    ? pintarTraza(datos) : pintarPorqueViejo(datos);
  $('#porque-caja').replaceChildren(caja);
}

// Al hacer clic en una burbuja del bot se vuelve a pintar el «por qué» de ESE
// turno y se resalta su burbuja. La memoria sigue viviendo en el servidor: aquí
// solo se guardan las trazas del hilo para poder repintarlas.
function mostrarTurno(idx) {
  if (!TURNOS[idx]) return;
  $$('#hilo .burbuja.activa').forEach((b) => b.classList.remove('activa'));
  $$(`#hilo .burbuja[data-turno="${idx}"]`).forEach((b) => b.classList.add('activa'));
  pintarPorque(TURNOS[idx]);
}

// ✓/✗ de un turno de guion. El servidor ya lo ha evaluado (misma definición que
// el banco); aquí solo se pinta. Cuenta para el resumen final del guion.
function marcarVeredicto(ev) {
  if (!ev || ev.error) return;
  TURNOS_GUION += 1;
  if (ev.ok) OK_GUION += 1;
  INV_GUION += (ev.fallos ? ev.fallos.length : 0);
  const chip = crear('div', 'veredicto ' + (ev.ok ? 'ok' : 'no'));
  chip.append(crear('span', 'v-marca', ev.ok ? '✓' : '✗'));
  chip.append(crear('span', 'v-txt', `esperado: ${ev.esperado} · obtenido: ${ev.obtenido}`));
  const extra = (ev.fallos && ev.fallos.length) ? ' · ' + ev.fallos.join('; ') : '';
  chip.title = `esperado: ${ev.esperado} · obtenido: ${ev.obtenido}${extra}`;
  $('#hilo').append(chip);
  $('#hilo').scrollTop = $('#hilo').scrollHeight;
}

/* --------------------------------------------------------------- enviar */
async function enviar(texto, guionRef = null) {
  if (OCUPADO || !texto.trim()) return;
  OCUPADO = true;
  $('#btn-enviar').disabled = true;
  burbuja(texto, 'enviada', false);
  escribiendo(true);

  try {
    const cuerpo = {
      sesion: SESION_ACTIVA, mensaje: texto, perfil: PERFIL,
      nombre: $('#nombre-cliente').value.trim(), reiniciar: PRIMERO,
    };
    if (guionRef) cuerpo.guion = guionRef;
    const datos = await api('/api/chat', cuerpo);
    PRIMERO = false;
    // Una pausa corta antes de contestar. No es decorado: sin ella las burbujas
    // aparecen a la vez que las tuyas y no se lee como una conversación.
    await pausa(420);
    escribiendo(false);
    const idx = TURNOS.push(datos) - 1;
    const lineas = datos.bot.lineas || [];
    for (let i = 0; i < lineas.length; i++) {
      const b = burbuja(lineas[i], 'recibida', i > 0);
      b.dataset.turno = String(idx);
      b.tabIndex = 0;
      b.setAttribute('role', 'button');
      b.title = 'Ver por qué contestó esto';
      b.addEventListener('click', () => mostrarTurno(idx));
      b.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); mostrarTurno(idx); }
      });
      if (i < lineas.length - 1) await pausa(320);
    }
    pintarBotones(datos.bot.opciones);
    if (datos.evaluacion) marcarVeredicto(datos.evaluacion);
    pintarPorque(datos);
  } catch (e) {
    escribiendo(false);
    burbuja(`[no se pudo responder: ${e.message}]`, 'recibida', false);
  } finally {
    OCUPADO = false;
    if (!REPRO.activo) $('#btn-enviar').disabled = false;
    if (!REPRO.activo) $('#chat-entrada').focus();
  }
}

/* --------------------------------------------------- guiones y reproductor */
const NOMBRES_TIPO = {
  compra: 'Compra directa', regatea: 'Regatea el precio', no_hay: 'No la tenemos',
  a_medias: 'Datos a medias', posventa: 'Va mal la pieza', taller: 'Pedido de taller',
  corrige: 'Se equivoca de coche', pago: 'Pago y envío',
};
const ORDEN_TIPO = ['compra', 'regatea', 'no_hay', 'a_medias', 'posventa',
                    'taller', 'corrige', 'pago'];
let GUIONES = [];

async function cargarGuiones() {
  let guiones;
  try { ({guiones} = await api('/api/guiones')); } catch { return; }
  GUIONES = guiones || [];
  const porTipo = {};
  GUIONES.forEach((g) => { (porTipo[g.tipo] = porTipo[g.tipo] || []).push(g); });

  const selT = $('#sel-tipo');
  selT.replaceChildren(...ORDEN_TIPO.filter((t) => porTipo[t]).map((t) => {
    const o = crear('option', null, `${NOMBRES_TIPO[t] || t} (${porTipo[t].length})`);
    o.value = t;
    return o;
  }));
  selT.onchange = llenarGuiones;
  $('#sel-guion').onchange = infoGuion;
  llenarGuiones();
}

// Cada guion aparece SOLO en su tipo principal (g.tipo); la mezcla se marca.
function llenarGuiones() {
  const t = $('#sel-tipo').value;
  const lista = GUIONES.filter((g) => g.tipo === t);
  $('#sel-guion').replaceChildren(...lista.map((g) => {
    const mezcla = (g.tipos_mezcla && g.tipos_mezcla.length) ? ' · mezcla' : '';
    const o = crear('option', null, `${g.id} · ${g.nombre}${mezcla}`);
    o.value = g.id;
    return o;
  }));
  infoGuion();
}

function guionSel() {
  return GUIONES.find((g) => g.id === $('#sel-guion').value) || null;
}

function infoGuion() {
  const g = guionSel();
  const el = $('#guion-info');
  if (!g) { el.textContent = ''; return; }
  const trato = g.perfil === 'conocido' ? 'de confianza' : 'nuevo';
  const mezcla = (g.tipos_mezcla && g.tipos_mezcla.length)
    ? ` · mezcla: ${g.tipos_mezcla.join(', ')}` : '';
  el.textContent = `Prueba: «${g.que_prueba}» · ${g.mensajes.length} mensajes · ${trato}${mezcla}`;
}

function modoReproduciendo(on) {
  $('#btn-parar').disabled = !on;
  $('#btn-reproducir').disabled = on;
  $('#sel-tipo').disabled = on;
  $('#sel-guion').disabled = on;
  $('#chat-entrada').disabled = on;
  $('#btn-enviar').disabled = on;
  $$('#perfil-cliente button').forEach((b) => { b.disabled = on; });
  // En «Paso a paso» el botón sigue activo para poder avanzar.
  $('#btn-paso').disabled = on && REPRO.modo !== 'paso';
}

async function arrancarGuion(modo) {
  const g = guionSel();
  if (!g || REPRO.activo) return;
  // El guion fija el perfil y el nombre: media conversación se explica por quién
  // escribe, y probar el guion de confianza como si fuera nuevo enseñaría un tono
  // que no es el suyo.
  ponerPerfil(g.perfil);
  if (g.cliente) $('#nombre-cliente').value = g.cliente;
  limpiarHilo();
  // Sesión propia del guion: `es_prueba` la excluye, así reproducirlo no deja
  // rastro en reservas.json ni en la cola de no resueltas (C6).
  SESION_ACTIVA = `guion-${g.id}-${Date.now()}`;
  Object.assign(REPRO, {activo: true, parar: false, guion: g, i: 0, modo});
  modoReproduciendo(true);
  if (modo === 'auto') await bucleAuto();
  else await pasoSiguiente();     // el primer paso
}

async function bucleAuto() {
  const g = REPRO.guion;
  while (REPRO.i < g.mensajes.length && !REPRO.parar) {
    await enviar(g.mensajes[REPRO.i], {id: g.id, turno: REPRO.i});
    REPRO.i += 1;
    if (REPRO.i < g.mensajes.length && !REPRO.parar) await pausa(700);
  }
  terminarGuion();
}

async function pasoSiguiente() {
  const g = REPRO.guion;
  if (!g || REPRO.i >= g.mensajes.length) { terminarGuion(); return; }
  await enviar(g.mensajes[REPRO.i], {id: g.id, turno: REPRO.i});
  REPRO.i += 1;
  if (REPRO.i >= g.mensajes.length) terminarGuion();
}

// Parar corta al terminar el turno en curso, sin dejar el chat bloqueado (§9.1).
function pararGuion() {
  if (!REPRO.activo) return;
  REPRO.parar = true;
  if (REPRO.modo === 'paso' && !OCUPADO) terminarGuion();
}

function terminarGuion() {
  if (!REPRO.activo) return;
  REPRO.activo = false;
  modoReproduciendo(false);
  if (TURNOS_GUION) {
    const linea = crear('div', 'resumen-guion');
    linea.textContent =
      `${OK_GUION}/${TURNOS_GUION} turnos OK · ${INV_GUION} invariantes rotos`;
    $('#hilo').append(linea);
    $('#hilo').scrollTop = $('#hilo').scrollHeight;
  }
}

function ponerPerfil(perfil) {
  PERFIL = perfil;
  $$('#perfil-cliente button').forEach((b) =>
    b.setAttribute('aria-pressed', String(b.dataset.perfil === perfil)));
  $('#mando-nombre').hidden = perfil !== 'conocido';
}

/* ---------------------------------------------------------------- init */
$$('#perfil-cliente button').forEach((b) => {
  b.onclick = () => { ponerPerfil(b.dataset.perfil); limpiarHilo(); };
});
$$('#vel-guion button').forEach((b) => {
  b.onclick = () => {
    VEL = b.dataset.vel;
    $$('#vel-guion button').forEach((x) =>
      x.setAttribute('aria-pressed', String(x === b)));
  };
});
$('#btn-reproducir').onclick = () => { if (!REPRO.activo) arrancarGuion('auto'); };
$('#btn-paso').onclick = () => {
  if (REPRO.activo && REPRO.modo === 'paso') pasoSiguiente();
  else if (!REPRO.activo) arrancarGuion('paso');
};
$('#btn-parar').onclick = pararGuion;
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && REPRO.activo) pararGuion();
});
$('#btn-reiniciar').onclick = () => { if (!REPRO.activo) limpiarHilo(); };
$('#form-chat').addEventListener('submit', (e) => {
  e.preventDefault();
  if (REPRO.activo) return;
  const texto = $('#chat-entrada').value.trim();
  $('#chat-entrada').value = '';
  enviar(texto);
});

limpiarHilo();
cargarGuiones();
