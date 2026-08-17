/* VendIQ · simulador de conversación de WhatsApp
   ------------------------------------------------------------------------
   El chat NO tiene lógica de negocio. Manda el mensaje al servidor y pinta lo
   que le devuelve: el texto, la regla que se aplicó y lo que el bot recuerda.
   La memoria de la conversación vive en Python, no aquí — si viviera en el
   navegador, recargar la página cambiaría lo que responde el bot, y entonces
   esto sería una maqueta y no una prueba. */

const SESION = `panel-${Date.now()}`;
let PERFIL = 'nuevo';
let OCUPADO = false;
let PRIMERO = true;          // el próximo mensaje reinicia la conversación

const hora = () => new Date().toLocaleTimeString('es-ES',
  {hour: '2-digit', minute: '2-digit'});

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

function limpiarHilo() {
  $('#hilo').replaceChildren(crear('div', 'dia', 'HOY'));
  $('#porque-caja').replaceChildren(
    crear('p', 'vacio', 'Manda un mensaje o elige una conversación tipo.'));
  PRIMERO = true;
}

/* -------------------------------------------------------------- por qué */
const SELLOS = {
  'RESPONDE':      ['ok', '✓ RESUELVE'],
  'NO DISPONIBLE': ['escala', '⊘ NO LA TENGO'],
  'ESCALA':        ['escala', '! A TU MESA'],
};

function pintarPorque(datos) {
  const {bot, busqueda, memoria} = datos;
  const caja = crear('div');

  const cab = crear('div', 'porque-cab');
  const [clase, texto] = SELLOS[busqueda.decision] || ['escala', busqueda.decision];
  cab.append(crear('span', 'sello ' + clase, texto));
  if (bot.escala) cab.append(crear('span', 'pastilla p-ambar', 'AVISA A ÁLVARO'));
  cab.append(crear('span', 'pastilla p-gris', bot.intencion));
  cab.append(crear('span', 'ms', `${busqueda.ms} ms`));
  caja.append(cab);

  // Lo que el bot recuerda de la conversación. Es la mitad del producto: sin
  // esto pediría la matrícula en cada mensaje.
  const mem = crear('div', 'memoria');
  const datosMem = [
    ['turno', memoria.turnos],
    ['trato', memoria.perfil === 'conocido' ? `${memoria.nombre || 'conocido'}, de confianza`
                                            : 'nuevo'],
    ['matrícula', memoria.matricula],
    ['coche', memoria.vehiculo],
    ['pieza sobre la mesa', memoria.pieza],
    ['en manos de Álvaro', memoria.escalado ? 'sí' : null],
  ].filter(([, v]) => v !== null && v !== undefined && v !== '');
  datosMem.forEach(([k, v]) => {
    const d = crear('span', 'dato');
    d.append(document.createTextNode(`${k}: `), crear('b', null, String(v)));
    mem.append(d);
  });
  caja.append(mem);

  if (busqueda.contexto) {
    const c = crear('div', 'contexto');
    c.append(document.createTextNode('No repitió el coche, así que se buscó con lo que ya había dicho: '));
    c.append(crear('code', null, busqueda.contexto));
    caja.append(c);
  }

  // El precio, siempre con su motivo. Si alguna vez se publicara uno que el
  // buscador no autorizó, sale en rojo: es el fallo que no puede pasar.
  const piezas = (busqueda.resultados || []).filter((r) => r.tipo === 'inventario');
  const pc = piezas.length ? piezas[0].precio_cliente : null;
  if (pc && pc.estado !== 'no_aplica') {
    const s = crear('div', 'sello-precio' + (bot.precio_autorizado ? '' : ' fuga'));
    s.append(pc.publicable ? crear('span', 'importe', pc.importe)
                           : crear('span', 'bloqueado', 'PRECIO RETENIDO'));
    s.append(crear('span', 'razon', bot.precio_autorizado ? pc.motivo
      : '¡FUGA! se ha publicado un importe que la búsqueda no autorizó'));
    caja.append(s);
  }

  caja.append(crear('p', 'porque-sub', 'Reglas aplicadas'));
  (bot.reglas || []).forEach((r) => {
    const bloque = crear('div', 'regla' +
      (/escalad|queja|no se reconoce/.test(r.regla) ? ' aviso' : ''));
    bloque.append(crear('p', 'que', r.regla), crear('p', 'detalle', r.detalle));
    caja.append(bloque);
  });

  if (piezas.length) {
    caja.append(crear('p', 'porque-sub', 'Fichas recuperadas'));
    piezas.forEach((r) => caja.append(fichaHTML(r, false)));
  }
  if ((busqueda.descartados || []).length) {
    caja.append(crear('p', 'porque-sub',
      `Descartadas por no llegar al umbral (${busqueda.descartados.length})`));
    busqueda.descartados.slice(0, 3).forEach((r) => caja.append(fichaHTML(r, true)));
  }

  $('#porque-caja').replaceChildren(caja);
}

/* --------------------------------------------------------------- enviar */
async function enviar(texto) {
  if (OCUPADO || !texto.trim()) return;
  OCUPADO = true;
  $('#btn-enviar').disabled = true;
  burbuja(texto, 'enviada', false);
  escribiendo(true);

  try {
    const datos = await api('/api/chat', {
      sesion: SESION, mensaje: texto, perfil: PERFIL,
      nombre: $('#nombre-cliente').value.trim(), reiniciar: PRIMERO,
    });
    PRIMERO = false;
    // Una pausa corta antes de contestar. No es decorado: sin ella las burbujas
    // aparecen a la vez que las tuyas y no se lee como una conversación.
    await new Promise((r) => setTimeout(r, 420));
    escribiendo(false);
    const lineas = datos.bot.lineas || [];
    for (let i = 0; i < lineas.length; i++) {
      burbuja(lineas[i], 'recibida', i > 0);
      if (i < lineas.length - 1) await new Promise((r) => setTimeout(r, 320));
    }
    pintarPorque(datos);
  } catch (e) {
    escribiendo(false);
    burbuja(`[no se pudo responder: ${e.message}]`, 'recibida', false);
  } finally {
    OCUPADO = false;
    $('#btn-enviar').disabled = false;
    $('#chat-entrada').focus();
  }
}

/* ------------------------------------------------------------- guiones */
async function cargarGuiones() {
  let guiones;
  try {
    ({guiones} = await api('/api/guiones'));
  } catch { return; }

  $('#guiones').replaceChildren(...guiones.map((g) => {
    const b = crear('button', 'chip', g.nombre);
    b.type = 'button';
    b.title = g.que_prueba;
    b.onclick = async () => {
      if (OCUPADO) return;
      // El guion fija también el perfil: media conversación se explica por quién
      // escribe, y probar el guion del cliente de confianza como si fuera nuevo
      // enseñaría un tono que no es el suyo.
      ponerPerfil(g.perfil);
      if (g.cliente) $('#nombre-cliente').value = g.cliente;
      limpiarHilo();
      $$('#guiones .chip').forEach((c) => c.classList.add('cargando'));
      for (const m of g.mensajes) {
        await enviar(m);
        await new Promise((r) => setTimeout(r, 700));
      }
      $$('#guiones .chip').forEach((c) => c.classList.remove('cargando'));
    };
    return b;
  }));
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
$('#btn-reiniciar').onclick = limpiarHilo;
$('#form-chat').addEventListener('submit', (e) => {
  e.preventDefault();
  const texto = $('#chat-entrada').value.trim();
  $('#chat-entrada').value = '';
  enviar(texto);
});

limpiarHilo();
cargarGuiones();
