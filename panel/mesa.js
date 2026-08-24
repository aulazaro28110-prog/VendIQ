/* VendIQ · la mesa de Álvaro
   ------------------------------------------------------------------------
   Todo lo que el bot no resolvió solo, en un sitio y agrupado por lo que hay
   que decidir. Los datos salen de /api/mesa; aquí no se calcula nada.

   POR QUÉ AGRUPADO Y NO POR FRECUENCIA
   ------------------------------------
   La lista plana anterior ordenaba por veces, y en la cola real medida las
   cuatro primeras eran «déjame que lo mire» (192), «luego te digo algo» (145),
   «ok, te confirmo mañana» (119) y «me lo quedo» (105) — ninguna necesita a
   nadie. Entre las cuatro tapaban «¿enviáis a Canarias?», que es la única con
   56 clientes esperando de verdad. Ordenar por volumen entierra lo que importa.

   COLOR
   -----
   Ámbar solo para lo que te necesita, cian para lo que el bot ya resuelve. El
   resto en tinta. El rojo no aparece: aquí no hay errores, hay trabajo. */

const GRUPO_ICONO = {
  posventa: '!', pago: '€', envio: '→', politica: '§',
  pieza: '?', conversacion: '✓', ruido: '·',
};

let MESA = null;
let VER_RESUELTAS = false;

/* --------------------------------------------------------------- cabecera */
function pintarResumenMesa(r) {
  const tiles = [
    ['Te necesitan', r.te_necesitan, r.te_necesitan ? 'ind aviso' : 'ind acento',
     r.te_necesitan ? 'nadie más puede contestarlas' : 'no hay nada esperándote'],
    ['Clientes esperando', r.clientes_esperando, 'ind',
     `en ${r.pendientes} preguntas distintas`],
    ['Ya las resuelve solo', r.ya_resueltas_solas, 'ind acento',
     'se apuntaron con un bot anterior'],
    ['Le has enseñado', r.aprendidas, 'ind acento',
     `${r.descartadas} descartadas sin enseñar nada`],
  ];
  $('#mesa-kpis').replaceChildren(...tiles.map(([et, cifra, clase, nota]) => {
    const caja = crear('div', clase);
    caja.append(crear('p', 'etiqueta', et),
                crear('p', 'cifra', String(cifra)),
                crear('p', 'nota', nota));
    return caja;
  }));
  $('#mesa-pie').textContent =
    `Comprobado contra el bot de ahora en ${r.ms} ms: a cada pregunta pendiente ` +
    `se le vuelve a pasar la búsqueda para saber si hoy seguiría escalándola.`;
}

/* ------------------------------------------------------------- una fila */
function filaMesa(f, grupo) {
  const fila = crear('div', 'duda' + (f.sigue_escalando ? '' : ' duda-resuelta'));

  const cab = crear('div', 'duda-cab');
  cab.append(crear('span', 'pastilla ' + (f.sigue_escalando ? 'p-ambar' : 'p-ok'),
                   `x${f.veces}`),
             crear('strong', null, `«${f.pregunta}»`));
  fila.append(cab);

  const meta = crear('p', 'duda-meta');
  meta.textContent = f.sigue_escalando
    ? `${f.motivo} · primera vez ${f.primera}`
    : `El bot de ahora la resuelve solo (${f.decision_ahora}). Quítala de la mesa.`;
  fila.append(meta);

  const acciones = crear('div', 'duda-responder');

  // Contestar solo tiene sentido si de verdad hace falta una persona. En los
  // grupos que el bot ya lleva, ofrecer un campo de respuesta invita a escribir
  // una FAQ para algo que no la necesita — y esa FAQ luego compite en el índice.
  if (f.sigue_escalando) {
    const campo = crear('textarea');
    campo.rows = 2;
    campo.placeholder = 'Escribe TÚ la respuesta. El bot la usará tal cual.';
    campo.setAttribute('aria-label', `Respuesta a: ${f.pregunta}`);
    const bt = crear('button', 'boton mini', 'Guardar y enseñársela');
    bt.onclick = async () => {
      const texto = campo.value.trim();
      if (!texto) { campo.focus(); return; }
      bt.disabled = true;
      try {
        const r = await api('/api/aprender', {n: f.n, respuesta: texto});
        fila.replaceChildren(Object.assign(crear('div', 'duda-ok'),
          {textContent: `Aprendida. ${r.indexado}`}));
        cargarMesa();
      } catch (e) { bt.disabled = false; alert(`No se pudo guardar: ${e.message}`); }
    };
    acciones.append(campo, bt);
  }

  const quitar = crear('button', 'boton mini sutil',
                       f.sigue_escalando ? 'No hace falta contestarla'
                                         : 'Quitar de la mesa');
  quitar.onclick = async () => {
    quitar.disabled = true;
    try {
      await api('/api/descartar', {n: f.n, motivo: grupo});
      fila.remove();
      cargarMesa();
    } catch (e) { quitar.disabled = false; alert(`No se pudo: ${e.message}`); }
  };
  acciones.append(quitar);

  fila.append(acciones);
  return fila;
}

/* ---------------------------------------------------------- los grupos */
function pintarGrupos(d) {
  const caja = $('#mesa-grupos');
  caja.replaceChildren();

  d.grupos.forEach((g) => {
    const filas = VER_RESUELTAS ? g.filas : g.filas.filter((f) => f.sigue_escalando);
    const decorativo = g.clave === 'ruido' || g.clave === 'conversacion';
    if (!filas.length && !decorativo) return;

    const carta = crear('section', 'carta grupo-mesa');
    const cab = crear('div', 'grupo-cab');
    cab.append(crear('span', 'grupo-icono', GRUPO_ICONO[g.clave] || '·'),
               crear('h3', null, g.titulo),
               crear('span', 'pastilla p-gris',
                     `${g.filas.length} · ${g.clientes} clientes`));
    carta.append(cab, crear('p', 'nota', g.nota));

    // Los dos grupos que no te necesitan van plegados: están para que veas que
    // no se han perdido, no para que los leas uno a uno.
    if (decorativo) {
      const det = crear('details');
      const sum = crear('summary');
      sum.textContent = `Ver las ${g.filas.length} y quitarlas`;
      det.append(sum);
      g.filas.forEach((f) => det.append(filaMesa(f, g.clave)));
      const todas = crear('button', 'boton mini sutil',
                          `Quitar las ${g.filas.length} de la mesa`);
      todas.onclick = async () => {
        todas.disabled = true;
        for (const f of g.filas) {
          try { await api('/api/descartar', {n: f.n, motivo: g.clave}); } catch {}
        }
        cargarMesa();
      };
      det.append(todas);
      carta.append(det);
    } else {
      filas.forEach((f) => carta.append(filaMesa(f, g.clave)));
    }
    caja.append(carta);
  });

  if (!caja.children.length) {
    caja.replaceChildren(Object.assign(crear('div', 'estado-vacio'), {
      innerHTML: '<strong>La mesa está vacía.</strong> El bot ha sabido llevar todo ' +
        'lo que le ha llegado.<br>Cuando alguien pregunte algo que no está en los ' +
        'documentos, aparecerá aquí agrupado y con su respuesta en blanco.',
    }));
  }
}

/* ------------------------------------------------------------------ init */
async function cargarMesa() {
  let d;
  try { d = await api('/api/mesa'); } catch { return; }
  MESA = d;
  pintarResumenMesa(d.resumen);
  pintarGrupos(d);
}

function pintarMandoMesa() {
  const b = $('#mesa-ver-resueltas');
  if (!b) return;
  b.setAttribute('aria-pressed', String(VER_RESUELTAS));
  b.onclick = () => {
    VER_RESUELTAS = !VER_RESUELTAS;
    pintarMandoMesa();
    if (MESA) pintarGrupos(MESA);
  };
}

pintarMandoMesa();
cargarMesa();
