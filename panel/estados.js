/* VendIQ · contadores por estado, desplegables
   ========================================================================
   PASO 4 y PASO 5 del retoque. Dos bloques con la misma forma: un contador
   grande por estado, con su color semántico, y al pulsarlo se abre la lista
   de lo que hay dentro.

     Mesa de negociación (#mesa-estados)  <- /api/ofertas
     Tu mesa             (#tumesa-estados) <- /api/mesa y /api/no-resueltas

   ADITIVO. No toca panel.js ni mesa.js: la tabla completa de ofertas y la
   mesa de siempre siguen donde estaban, con sus ganchos y sus botones. Esto
   se pinta en huecos nuevos. Si este fichero falla, se pierden los
   contadores y no se pierde ni un dato: todo sigue accesible abajo.

   CERO DATOS INVENTADOS. Los números son cuentas sobre lo que devuelve la
   API. Un estado que no tiene nada dentro no se dibuja, en vez de enseñar un
   cero que parece un fallo. Y si no hay nada de nada, lo dice y explica qué
   hacer para que lo haya. */

const abrirCerrar = (cab, panel) => {
  const abierto = cab.getAttribute('aria-expanded') === 'true';
  cab.setAttribute('aria-expanded', abierto ? 'false' : 'true');
  // La altura real, para que la transición tenga a dónde ir. `auto` no anima.
  panel.style.maxHeight = abierto ? '0px' : panel.scrollHeight + 'px';
  panel.classList.toggle('abierto', !abierto);
};

/* Un contador desplegable. `filas` es una función que devuelve los nodos de
   la lista: se llama solo al construir, pero se mantiene perezosa para no
   montar listas de estados que estén vacíos. */
function bloqueEstado({clave, titulo, n, tono, pie, filas}) {
  const caja = crear('div', 'estado estado-' + tono);

  const cab = crear('button', 'estado-cab');
  cab.type = 'button';
  cab.setAttribute('aria-expanded', 'false');
  cab.id = 'est-' + clave;

  const izda = crear('div', 'estado-txt');
  izda.append(crear('p', 'estado-eti', titulo));
  const cifra = crear('p', 'estado-n');
  cifra.textContent = String(n);
  izda.append(cifra);
  if (pie) izda.append(crear('p', 'estado-pie', pie));

  cab.append(izda, crear('span', 'estado-flecha'));
  caja.append(cab);

  const panel = crear('div', 'estado-panel');
  panel.setAttribute('role', 'region');
  panel.setAttribute('aria-labelledby', cab.id);
  panel.style.maxHeight = '0px';
  filas().forEach((f) => panel.append(f));
  caja.append(panel);

  cab.onclick = () => abrirCerrar(cab, panel);
  return caja;
}

function filaOferta(o) {
  const f = crear('div', 'estado-fila');
  const izda = crear('div');
  izda.append(crear('b', null, o.descripcion || ('Pieza ' + (o.id_pieza || '—'))));
  const meta = crear('span', 'estado-meta');
  meta.textContent = [o.cliente, o.antiguedad].filter(Boolean).join(' · ');
  izda.append(meta);
  f.append(izda);

  const dcha = crear('div', 'estado-cifras');
  if (o.precio_lista) {
    dcha.append(crear('span', 'estado-tacha', eur(o.precio_lista)));
  }
  dcha.append(crear('b', null, eur(o.importe)));
  if (o.descuento != null) {
    dcha.append(crear('span', 'estado-dto', '−' + pct(o.descuento)));
  }
  f.append(dcha);
  if (o.motivo) f.title = o.motivo;
  return f;
}

/* ------------------------------------------------ mesa de negociación */
async function pintarEstadosOfertas() {
  const destino = $('#mesa-estados');
  if (!destino) return;

  let ofertas;
  try {
    const d = await api('/api/ofertas');
    ofertas = Array.isArray(d) ? d : (d.ofertas || []);
  } catch (e) {
    destino.replaceChildren(Object.assign(crear('div', 'estado-vacio fallo'),
      {textContent: 'No se pudieron leer las ofertas: ' + e.message}));
    return;
  }

  if (!ofertas.length) {
    const v = crear('div', 'estado-vacio');
    v.append(crear('strong', null, 'Todavía no hay ninguna oferta.'),
             document.createTextNode(' Lanza una arriba, o desde la línea de '),
             crear('code', null, 'python 04_ofertas.py oferta 69183 780'));
    destino.replaceChildren(v);
    return;
  }

  const de = (d) => ofertas.filter((o) => o.decision === d);
  const pendientes = ofertas.filter((o) => o.estado === 'pendiente');

  const bloques = [
    {clave: 'recibidas', titulo: 'Recibidas', n: ofertas.length, tono: 'neutro',
     pie: 'todas las que han entrado', filas: () => ofertas.map(filaOferta)},
    {clave: 'aceptadas', titulo: 'Aceptadas', n: de('ACEPTAR').length, tono: 'bien',
     pie: 'la regla las cerró sola', filas: () => de('ACEPTAR').map(filaOferta)},
    {clave: 'rechazadas', titulo: 'Rechazadas', n: de('RECHAZAR').length,
     tono: 'critico', pie: 'por debajo del mínimo',
     filas: () => de('RECHAZAR').map(filaOferta)},
  ];

  // "Esperan tu decisión" solo si de verdad hay alguna. No estaba en la lista
  // de tres, pero es el único estado que PIDE algo: esconderlo cuando hay
  // ofertas paradas sería esconder trabajo pendiente.
  if (pendientes.length) {
    bloques.push({clave: 'pendientes', titulo: 'Esperan tu decisión',
      n: pendientes.length, tono: 'aviso', pie: 'la regla no las cierra sola',
      filas: () => pendientes.map(filaOferta)});
  }

  destino.replaceChildren(...bloques
    .filter((b) => b.n > 0 || b.clave === 'recibidas')
    .map(bloqueEstado));
}

/* ---------------------------------------------------------- tu mesa */
function filaPendiente(p) {
  const f = crear('div', 'estado-fila');
  const izda = crear('div');
  izda.append(crear('b', null, p.pregunta || p.consulta || '—'));
  const meta = crear('span', 'estado-meta');
  meta.textContent = [p.motivo, p.veces ? p.veces + ' veces' : '']
    .filter(Boolean).join(' · ');
  izda.append(meta);
  f.append(izda);
  if (p.decision) {
    const dcha = crear('div', 'estado-cifras');
    dcha.append(crear('span', 'pastilla ' +
      (p.decision === 'ESCALA' ? 'p-ambar' : 'p-violeta'), p.decision));
    f.append(dcha);
  }
  return f;
}

async function pintarEstadosMesa() {
  const destino = $('#tumesa-estados');
  if (!destino) return;

  let sin;
  try {
    const d = await api('/api/no-resueltas');
    sin = Array.isArray(d) ? d : (d.no_resueltas || d.pendientes || []);
  } catch (e) {
    destino.replaceChildren(Object.assign(crear('div', 'estado-vacio fallo'),
      {textContent: 'No se pudo leer la mesa: ' + e.message}));
    return;
  }

  if (!sin.length) {
    const v = crear('div', 'estado-vacio');
    v.append(crear('strong', null, 'Nada pendiente.'),
             document.createTextNode(' El bot no ha dejado ninguna sin contestar.'));
    destino.replaceChildren(v);
    return;
  }

  // Por motivo, que es como de verdad se reparte el trabajo: no es lo mismo
  // una decisión de negocio que una duda del bot.
  const porMotivo = new Map();
  sin.forEach((p) => {
    const k = p.motivo || 'sin motivo';
    if (!porMotivo.has(k)) porMotivo.set(k, []);
    porMotivo.get(k).push(p);
  });

  const total = sin.reduce((a, p) => a + (p.veces || 1), 0);

  // Dos órdenes, y los dos útiles de verdad: por cuántas veces la han
  // preguntado (contestar esa rinde más) o por cuánto lleva esperando (que es
  // la que lleva más tiempo dando la lata). Por defecto, la más preguntada.
  const ORDENES = {
    veces: ['Más preguntadas', (a, b) => (b.veces || 0) - (a.veces || 0)],
    antiguas: ['Más antiguas', (a, b) =>
      String(a.primera || '').localeCompare(String(b.primera || ''))],
  };
  let orden = 'veces';

  const listaOrdenada = () => [...sin].sort(ORDENES[orden][1]).map(filaPendiente);

  const control = crear('div', 'estado-orden');
  Object.entries(ORDENES).forEach(([k, [etiqueta]]) => {
    const bt = crear('button', 'chip' + (k === orden ? ' activo' : ''), etiqueta);
    bt.type = 'button';
    bt.setAttribute('aria-pressed', k === orden ? 'true' : 'false');
    bt.onclick = (ev) => {
      ev.stopPropagation();                    // no cierra el desplegable
      orden = k;
      control.querySelectorAll('.chip').forEach((o) => {
        const activo = o === bt;
        o.classList.toggle('activo', activo);
        o.setAttribute('aria-pressed', activo ? 'true' : 'false');
      });
      const panel = control.closest('.estado-panel');
      if (!panel) return;
      panel.replaceChildren(control, ...listaOrdenada());
      if (panel.classList.contains('abierto')) {
        panel.style.maxHeight = panel.scrollHeight + 'px';
      }
    };
    control.append(bt);
  });

  const bloques = [{
    clave: 'te-necesitan', titulo: 'Te necesitan', n: sin.length, tono: 'aviso',
    pie: total + ' veces preguntado en total',
    filas: () => [control, ...listaOrdenada()],
  }];

  [...porMotivo.entries()]
    .sort((a, b) => b[1].length - a[1].length)
    .forEach(([motivo, lista], i) => {
      bloques.push({
        clave: 'motivo-' + i,
        titulo: motivo.length > 46 ? motivo.slice(0, 44) + '…' : motivo,
        n: lista.length, tono: i === 0 ? 'neutro' : 'pregunta',
        pie: 'agrupadas por el motivo que las trajo',
        filas: () => lista.map(filaPendiente),
      });
    });

  destino.replaceChildren(...bloques.map(bloqueEstado));
}

/* ------------------------------------------- los badges de la barra
   Se rellenan aquí y no en tema.js por dos razones: tema.js va en el <head>,
   antes de que exista api(), y estos números salen de peticiones que este
   fichero YA hace. Pedirlos otra vez sería trabajo doble por un número.

   La regla, literal: si no hay dato o la cuenta es cero, el badge se queda
   oculto. Hoy solo "Tu mesa" tiene algo detrás — las ofertas están todas
   cerradas y del chat no existe ningún contador de no leídos en ninguna API.
   Los tres huecos están puestos igualmente: el día que haya dato, aparecen
   solos sin tocar el HTML. */
function ponerBadge(cual, n, tono) {
  // Por el ATRIBUTO data-badge, no por la clase: así cubre a la vez el de
  // nav.barra (.nav-badge) y el que barra.js clona en la lateral (.sb-badge).
  const badges = document.querySelectorAll('[data-badge="' + cual + '"]');
  const TONOS = ['aviso', 'bien', 'pregunta', 'critico'];
  badges.forEach((b) => {
    if (!n) { b.hidden = true; return; }       // 0, null o undefined: nada
    b.textContent = n > 99 ? '99+' : String(n);
    b.classList.remove(...TONOS);               // sin pisar la clase base
    if (tono) b.classList.add(tono);
    b.hidden = false;
  });
}

(async () => {
  try {
    const d = await api('/api/no-resueltas');
    const lista = Array.isArray(d) ? d : (d.pendientes || []);
    // Solo las que de verdad esperan: las resueltas y las descartadas ya no
    // te necesitan, y contarlas inflaría el badge con trabajo hecho.
    const esperan = lista.filter((p) => !p.estado || p.estado === 'pendiente');
    ponerBadge('mesa', esperan.length, 'aviso');
  } catch (e) { /* sin dato, sin badge */ }

  try {
    const d = await api('/api/ofertas');
    const ofertas = Array.isArray(d) ? d : (d.ofertas || []);
    ponerBadge('ofertas', ofertas.filter((o) => o.estado === 'pendiente').length,
               'aviso');
  } catch (e) { /* sin dato, sin badge */ }
})();

pintarEstadosOfertas();
pintarEstadosMesa();
