/* VendIQ · la fila de indicadores
   ------------------------------------------------------------------------
   ESTO NO PINTA NINGÚN DATO. Lo pinta panel.js en `pintarKPIs()`, igual que
   siempre; este fichero DECORA lo que ya está en pantalla: le pone el icono
   en círculo, anima la cifra desde cero y le cuelga una mini-gráfica.

   Se hace así a propósito. Reescribir `pintarKPIs()` para que además dibuje
   sería meter presentación dentro de la función que lee el resumen del
   servidor, y a la primera que cambie una el otro se rompe. Con un observador
   encima, si este fichero falla o no carga, la fila de KPIs sigue estando
   completa y correcta: solo estará sin adornar.

   DE DÓNDE SALEN LAS MINI-GRÁFICAS
   --------------------------------
   De /api/actividad, que trae `por_dia`: siete días con conversaciones,
   resueltas, escaladas y latencia mediana. Es serie temporal de verdad.

   Y de ahí sale también el delta: es la variación real del último día
   respecto al anterior. Los indicadores que NO tienen serie —acierto
   verificado, ofertas cerradas solas— se quedan SIN flecha. Una flecha
   inventada en un panel que presume de medir todo sería la peor mentira
   posible aquí. */

/* Qué mini-gráfica y qué icono lleva cada indicador, buscándolo por su
   etiqueta, que es lo que panel.js escribe. Si mañana cambia una etiqueta,
   ese indicador se queda sin adorno; no se rompe nada. */
const KPI_MAPA = {
  'Resueltas sin persona': {ico: '✓', color: '', serie: 'resueltas', delta: true},
  'Tiempo de respuesta':   {ico: '◷', color: 'violeta', serie: 'ms_mediana',
                            delta: true, menosEsMejor: true},
  'Ofertas cerradas solas': {ico: '⇄', color: 'ambar', serie: null, delta: false},
  'Acierto verificado':    {ico: '◎', color: '', serie: null, delta: false},
};

let POR_DIA = null;

/* ------------------------------------------------------------- count-up */
/* Se respeta el texto EXACTO que escribió panel.js: se guarda, se anima
   sobre una copia y al acabar se restaura. Así un "95,9%" no acaba
   convertido en "95.9" por el camino. */
function contarHasta(el) {
  const final = el.firstChild && el.firstChild.nodeType === 3
    ? el.firstChild.nodeValue : el.textContent;
  const m = String(final).match(/-?[\d.,]+/);
  if (!m) return;

  const crudo = m[0];
  const decimales = (crudo.split(/[.,]/)[1] || '').length;
  const separador = crudo.includes(',') ? ',' : '.';
  const destino = parseFloat(crudo.replace(',', '.'));
  if (!isFinite(destino)) return;

  if (window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const nodo = el.firstChild;
  const empieza = performance.now();
  const dura = 700;

  const paso = (ahora) => {
    const t = Math.min(1, (ahora - empieza) / dura);
    const suave = 1 - Math.pow(1 - t, 3);          // ease-out cúbica
    const valor = (destino * suave).toFixed(decimales).replace('.', separador);
    nodo.nodeValue = String(final).replace(crudo, valor);
    if (t < 1) requestAnimationFrame(paso);
    else nodo.nodeValue = final;                    // el texto exacto, al final
  };
  nodo.nodeValue = String(final).replace(crudo, (0).toFixed(decimales)
    .replace('.', separador));
  requestAnimationFrame(paso);
}

/* ----------------------------------------------------------- sparkline */
function sparkline(valores, menosEsMejor) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  const an = 100, al = 30;
  svg.setAttribute('viewBox', `0 0 ${an} ${al}`);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('aria-hidden', 'true');

  const min = Math.min(...valores), max = Math.max(...valores);
  const rango = max - min || 1;
  const x = (i) => (i / (valores.length - 1)) * an;
  const y = (v) => al - 2 - ((v - min) / rango) * (al - 5);
  const puntos = valores.map((v, i) => [x(i), y(v)]);
  const d = puntos.map(([px, py], i) => (i ? 'L' : 'M') + px.toFixed(1)
    + ' ' + py.toFixed(1)).join(' ');

  const id = 'sp' + Math.random().toString(36).slice(2, 8);
  const defs = document.createElementNS(ns, 'defs');
  const grad = document.createElementNS(ns, 'linearGradient');
  grad.setAttribute('id', id);
  grad.setAttribute('x1', '0'); grad.setAttribute('y1', '0');
  grad.setAttribute('x2', '0'); grad.setAttribute('y2', '1');
  [['0%', '.35'], ['100%', '0']].forEach(([off, op]) => {
    const s = document.createElementNS(ns, 'stop');
    s.setAttribute('offset', off);
    s.setAttribute('stop-color', 'currentColor');
    s.setAttribute('stop-opacity', op);
    grad.append(s);
  });
  defs.append(grad);

  const area = document.createElementNS(ns, 'path');
  area.setAttribute('d', `${d} L ${an} ${al} L 0 ${al} Z`);
  area.setAttribute('fill', `url(#${id})`);

  const linea = document.createElementNS(ns, 'path');
  linea.setAttribute('d', d);
  linea.setAttribute('fill', 'none');
  linea.setAttribute('stroke', 'currentColor');
  linea.setAttribute('stroke-width', '1.6');
  linea.setAttribute('stroke-linejoin', 'round');
  linea.setAttribute('stroke-linecap', 'round');
  linea.setAttribute('vector-effect', 'non-scaling-stroke');

  // El punto final, 4 px REDONDOS. No puede ser un <circle>: el viewBox se
  // estira en horizontal (preserveAspectRatio="none") y el circulo saldria
  // ovalado. Un subtrazo de longitud cero con remate redondo y
  // vector-effect:non-scaling-stroke se dibuja en pixeles de pantalla, asi
  // que sale redondo mida lo que mida la tarjeta.
  const [fx, fy] = puntos[puntos.length - 1];
  const fin = document.createElementNS(ns, 'path');
  fin.setAttribute('class', 'sp-fin');
  fin.setAttribute('d', 'M ' + fx.toFixed(1) + ' ' + fy.toFixed(1)
                      + ' L ' + fx.toFixed(1) + ' ' + fy.toFixed(1));
  fin.setAttribute('fill', 'none');
  fin.setAttribute('stroke', 'currentColor');
  fin.setAttribute('stroke-width', '4');
  fin.setAttribute('stroke-linecap', 'round');
  fin.setAttribute('vector-effect', 'non-scaling-stroke');

  svg.append(defs, area, linea, fin);
  // Un solo acento: la sparkline no codifica nada con el color —codifica con
  // la forma—, así que las cuatro van en --accent. La azul de antes daba a
  // entender un estado que no existe.
  svg.style.color = 'var(--accent)';
  return svg;
}

/* --------------------------------------------------------------- delta */
function delta(valores, menosEsMejor) {
  if (valores.length < 2) return null;
  const hoy = valores[valores.length - 1], ayer = valores[valores.length - 2];
  if (!ayer) return null;
  const variacion = ((hoy - ayer) / Math.abs(ayer)) * 100;
  if (!isFinite(variacion)) return null;

  const sube = variacion > 0;
  const bueno = menosEsMejor ? !sube : sube;
  const chip = crear('span', 'kpi-delta'
    + (Math.abs(variacion) < 0.05 ? ' neutro' : bueno ? '' : ' baja'));
  chip.textContent = (sube ? '↑' : '↓') + ' '
    + Math.abs(variacion).toFixed(1).replace('.', ',') + '%';

  /* El tooltip del panel es `data-tip`, no el `title` del navegador: ése lo
     dibuja cada sistema a su manera y tarda medio segundo en salir, así que
     el mismo dato se veía de tres formas distintas según la máquina.

     Como data-tip se pinta con CSS y un lector de pantalla no lo lee, la
     explicación va ADEMÁS en aria-label, junto al valor. Y el chip se hace
     enfocable para que quien va con el teclado también lo alcance. */
  const explica = 'Último día frente al anterior, de los 7 medidos';
  chip.setAttribute('data-tip', explica);
  chip.setAttribute('tabindex', '0');
  chip.setAttribute('aria-label', chip.textContent + ' — ' + explica);
  return chip;
}

/* ------------------------------------------------------------- decorar */
function decorarKPIs() {
  document.querySelectorAll('#kpis .ind').forEach((caja) => {
    if (caja.dataset.decorado) return;
    caja.dataset.decorado = '1';

    const eti = caja.querySelector('.etiqueta');
    const cifra = caja.querySelector('.cifra');
    if (!eti || !cifra) return;
    const conf = KPI_MAPA[eti.textContent.trim()];

    caja.classList.add('entra');

    if (conf) {
      // El icono, envolviendo la etiqueta sin tocarla.
      const cab = crear('div', 'kpi-cab');
      const ico = crear('div', 'kpi-ico' + (conf.color ? ' ' + conf.color : ''),
                        conf.ico);
      eti.replaceWith(cab);
      cab.append(ico, eti);

      if (POR_DIA && conf.serie) {
        const valores = POR_DIA.map((d) => d[conf.serie]).filter((v) => v != null);
        if (valores.length > 1) {
          if (conf.delta) {
            const chip = delta(valores, conf.menosEsMejor);
            if (chip) cifra.after(chip);
          }
          const viz = crear('div', 'kpi-viz');
          viz.append(sparkline(valores, conf.menosEsMejor));
          caja.append(viz);
        }
      }
    }
    contarHasta(cifra);
  });
}

/* Un observador, y no un parche dentro de pintarKPIs(): así panel.js sigue
   sin saber que esto existe. */
function vigilarKPIs() {
  const zona = $('#kpis');
  if (!zona) return;
  decorarKPIs();
  new MutationObserver(() => decorarKPIs()).observe(zona, {childList: true});
}

(async () => {
  try {
    const d = await api('/api/actividad');
    if (d && Array.isArray(d.por_dia)) POR_DIA = d.por_dia;
  } catch (e) {
    // Sin serie no hay sparkline ni delta. La fila sigue estando bien.
  }
  vigilarKPIs();
})();
