/* VendIQ · acabado
   ========================================================================
   Esqueletos mientras llegan los datos, entrada escalonada de las tarjetas y
   chips de estado en el feed. Aditivo como kpi.js y graficas.js: nada de esto
   pinta un dato, solo se pone encima de lo que ya pintaron panel.js y
   actividad.js.

   EL TRUCO DE LOS ESQUELETOS
   --------------------------
   No hace falta avisar a nadie de que los datos llegaron: las funciones que
   pintan usan `replaceChildren()`, así que barren el esqueleto ellas solas al
   poner lo suyo. Este fichero solo tiene que meterlo al principio.

   Lo que sí hace falta es un PLAN B: si los datos no llegan nunca —servidor
   caído, fetch fallido— un esqueleto latiendo para siempre es mentir con
   estilo. A los 12 segundos se convierte en un estado vacío que dice qué
   pasa y qué hacer. */

const HUECOS = [
  ['#kpis',        4, 'ind',
   'No llegaron las cifras. ¿Sigue vivo 06_panel.py?'],
  ['#hero-cifras', 3, 'stat',
   'No llegaron las cifras de cabecera.'],
  ['#g-dias',      1, 'alto',
   'Sin días medidos. Ejecuta 10_simular.py --dias 7.'],
  ['#diagrama',    1, 'alto',
   'Sin recorrido que dibujar.'],
  ['#muestra-conv', 2, 'medio',
   'Sin conversaciones de muestra.'],
];

function meterEsqueletos() {
  HUECOS.forEach(([sel, n, forma, aviso]) => {
    const hueco = document.querySelector(sel);
    if (!hueco || hueco.children.length) return;      // ya tiene algo: fuera
    for (let i = 0; i < n; i++) {
      hueco.append(Object.assign(
        document.createElement('div'),
        {className: 'esqueleto esq-' + forma}));
    }
    // El plan B. Solo actúa si a los 12 s SIGUE habiendo esqueleto, es decir
    // si nadie ha llamado a replaceChildren() por encima.
    setTimeout(() => {
      if (!hueco.querySelector('.esqueleto')) return;
      const caja = document.createElement('p');
      caja.className = 'vacio';
      caja.textContent = aviso;
      hueco.replaceChildren(caja);
    }, 12000);
  });
}

/* ------------------------------------------------- entrada escalonada
   Desde estado VISIBLE, no desde opacity:0 esperando un scroll: si el
   observador no dispara —pestaña en segundo plano, navegador viejo— la página
   se queda en blanco y parece rota. Aquí la tarjeta ya está, solo se asienta.

   Y solo las de la primera pantalla. Animar treinta tarjetas a la vez es
   ruido, y las de abajo nadie las ve entrar. */
function escalonar() {
  if (window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const alto = window.innerHeight * 1.15;
  let n = 0;
  document.querySelectorAll('.carta, .ind').forEach((el) => {
    if (el.closest('#outlook')) return;               // el correo entra solo
    if (el.getBoundingClientRect().top > alto) return;
    if (n >= 8) return;
    el.style.animationDelay = (n * 55) + 'ms';
    el.classList.add('entra');
    n++;
  });
}

/* ------------------------------------------------ chips del feed
   El color sale de las ACCIONES reales de la conversación, no de una
   clasificación inventada: si en algún turno hubo ESCALAR es que acabó en tu
   mesa; si hubo PREGUNTAR, el bot tuvo que pedir un dato; si no, la resolvió
   del tirón. Los tres son datos que ya están en actividad.json. */
const CHIP = {
  ESCALAR:   ['p-ambar', 'acabó en tu mesa'],
  PREGUNTAR: ['p-violeta', 'tuvo que preguntar'],
  RESPONDER: ['p-ok', 'resuelta del tirón'],
};

function chiparFeed(muestra) {
  const cajas = document.querySelectorAll('#muestra-conv .conv-muestra');
  if (!cajas.length || !muestra) return false;

  cajas.forEach((caja, i) => {
    if (caja.dataset.chipada) return;
    const m = muestra[i];
    if (!m || !Array.isArray(m.turnos)) return;
    caja.dataset.chipada = '1';

    const acciones = new Set(m.turnos.map((t) => t.accion));
    const cual = acciones.has('ESCALAR') ? 'ESCALAR'
      : acciones.has('PREGUNTAR') ? 'PREGUNTAR' : 'RESPONDER';
    const [clase, texto] = CHIP[cual];

    const cab = caja.querySelector('.conv-cab');
    if (!cab) return;
    const chip = document.createElement('span');
    chip.className = 'pastilla ' + clase;
    chip.textContent = texto;
    // Antes de la hora, que va empujada a la derecha.
    const hora = cab.querySelector('.conv-hora');
    if (hora) cab.insertBefore(chip, hora); else cab.append(chip);
  });
  return true;
}

/* ================================================================ arranque */
meterEsqueletos();

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', escalonar);
} else {
  escalonar();
}

(async () => {
  let a = null;
  try { a = await api('/api/actividad'); } catch (e) { return; }
  if (!a || !Array.isArray(a.muestra)) return;
  // La muestra la pinta actividad.js filtrando las FUGA y cortando a 6: hay
  // que chipar con la MISMA lista o los colores se irían a otra conversación.
  const lista = a.muestra.filter((m) => !m.FUGA).slice(0, 6);
  let intentos = 0;
  const probar = () => {
    if (chiparFeed(lista)) return;
    if (++intentos < 40) setTimeout(probar, 150);     // 6 s y se rinde
  };
  probar();
})();
