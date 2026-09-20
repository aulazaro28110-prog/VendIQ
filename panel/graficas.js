/* VendIQ · las gráficas
   ========================================================================
   SVG a mano, sin librería. No es cabezonería: panel.css declara que el panel
   funciona SIN INTERNET (por eso la tipografía no viene de Google Fonts), y
   una gráfica por CDN rompe esa propiedad — sin conexión desaparecerían. En
   una entrevista "funciona sin red" vale más que un tooltip regalado.

   ADITIVO, como kpi.js
   --------------------
   actividad.js sigue pintando lo que pintaba. Este fichero SUSTITUYE después
   el contenido de #g-dias por el área, y añade anillos y gauge en huecos
   nuevos. Si este fichero no carga o revienta, en #g-dias se quedan las
   barras apiladas de siempre, que son correctas: se pierde el adorno, no el
   dato. Por eso no se toca actividad.js.

   CERO DATOS INVENTADOS
   ---------------------
   Todo sale de /api/actividad y /api/estado. Ni un número escrito aquí. Si
   una medida no llega, ese hueco se queda con su estado vacío en vez de
   rellenarse. */

const NS = 'http://www.w3.org/2000/svg';
const svgEl = (tag, attrs = {}) => {
  const el = document.createElementNS(NS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
};
const idUnico = (p) => p + Math.random().toString(36).slice(2, 8);
const sinMovimiento = () => window.matchMedia
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ============================================================ el área
   Conversaciones por día. Curva suave (Catmull-Rom pasada a Bézier), relleno
   con degradado, punto final destacado y tooltip al pasar el ratón.

   El domingo vale 0 porque el desguace CIERRA, y eso no es un hueco de datos:
   se dibuja como cero de verdad y el tooltip lo dice. Interpolarlo sería
   inventarse tráfico un día que no abre. */
function curva(puntos, tension = 0.5) {
  if (puntos.length < 2) return '';
  let d = `M ${puntos[0][0].toFixed(2)} ${puntos[0][1].toFixed(2)}`;
  for (let i = 0; i < puntos.length - 1; i++) {
    const p0 = puntos[i - 1] || puntos[i];
    const p1 = puntos[i];
    const p2 = puntos[i + 1];
    const p3 = puntos[i + 2] || p2;
    const c1x = p1[0] + ((p2[0] - p0[0]) / 6) * tension;
    const c1y = p1[1] + ((p2[1] - p0[1]) / 6) * tension;
    const c2x = p2[0] - ((p3[0] - p1[0]) / 6) * tension;
    const c2y = p2[1] - ((p3[1] - p1[1]) / 6) * tension;
    d += ` C ${c1x.toFixed(2)} ${c1y.toFixed(2)}, ${c2x.toFixed(2)} ${c2y.toFixed(2)},`
       + ` ${p2[0].toFixed(2)} ${p2[1].toFixed(2)}`;
  }
  return d;
}

function pintarArea(dias) {
  const destino = $('#g-dias');
  if (!destino || !dias || dias.length < 2) return;

  const AN = 720, AL = 260;
  const M = {arriba: 18, derecha: 16, abajo: 34, izda: 44};
  const anU = AN - M.izda - M.derecha;
  const alU = AL - M.arriba - M.abajo;

  const valores = dias.map((d) => d.conversaciones);
  const max = Math.max(...valores, 1);
  const tope = Math.ceil(max / 50) * 50 || 50;

  const x = (i) => M.izda + (i / (dias.length - 1)) * anU;
  const y = (v) => M.arriba + alU - (v / tope) * alU;
  const puntos = valores.map((v, i) => [x(i), y(v)]);

  const svg = svgEl('svg', {
    viewBox: `0 0 ${AN} ${AL}`,
    class: 'g-area',
    role: 'img',
    'aria-label': `Conversaciones por día: ${valores.join(', ')}`,
  });

  // Rejilla y eje. Cuatro líneas, que más es ruido.
  for (let i = 0; i <= 4; i++) {
    const v = (tope / 4) * i;
    svg.append(svgEl('line', {
      x1: M.izda, x2: AN - M.derecha, y1: y(v), y2: y(v),
      stroke: 'var(--border)', 'stroke-width': 1, 'stroke-opacity': .4,
    }));
    const t = svgEl('text', {
      x: M.izda - 10, y: y(v) + 4, 'text-anchor': 'end', class: 'g-eje',
    });
    t.textContent = String(Math.round(v));
    svg.append(t);
  }

  const gid = idUnico('ar');
  const defs = svgEl('defs');
  const grad = svgEl('linearGradient', {id: gid, x1: 0, y1: 0, x2: 0, y2: 1});
  [['0%', '.18'], ['100%', '0']].forEach(([offset, op]) => {
    grad.append(svgEl('stop', {
      offset, 'stop-color': 'var(--accent)', 'stop-opacity': op,
    }));
  });
  defs.append(grad);
  svg.append(defs);

  const d = curva(puntos);
  const area = svgEl('path', {
    d: `${d} L ${x(dias.length - 1)} ${y(0)} L ${x(0)} ${y(0)} Z`,
    fill: `url(#${gid})`,
  });
  const linea = svgEl('path', {
    d, fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2,
    'stroke-linecap': 'round', 'stroke-linejoin': 'round', class: 'g-linea',
  });
  svg.append(area, linea);

  // Un punto por día; el último, destacado.
  // Sin halo. Solo el punto final se destaca, a 4 px; los otros seis son la
  // marca minima para que el tooltip tenga a que agarrarse.
  puntos.forEach(([px, py], i) => {
    const ultimo = i === puntos.length - 1;
    svg.append(svgEl('circle', {
      cx: px, cy: py, r: ultimo ? 4 : 2.5,
      fill: ultimo ? 'var(--accent)' : 'var(--surface)',
      stroke: 'var(--accent)', 'stroke-width': ultimo ? 0 : 1.5,
    }));
    const et = svgEl('text', {
      x: px, y: AL - 12, 'text-anchor': 'middle', class: 'g-eje',
    });
    et.textContent = dias[i].fecha.slice(8) + '/' + dias[i].fecha.slice(5, 7);
    svg.append(et);
  });

  // La línea guía y la zona sensible del tooltip.
  const guia = svgEl('line', {
    y1: M.arriba, y2: M.arriba + alU, stroke: 'var(--borde-vivo)',
    'stroke-width': 1, 'stroke-dasharray': '3 3', class: 'g-guia', opacity: 0,
  });
  svg.append(guia);

  const envoltorio = crear('div', 'g-area-caja');
  const globo = crear('div', 'g-globo');
  globo.hidden = true;
  envoltorio.append(svg, globo);

  const mover = (ev) => {
    const caja = svg.getBoundingClientRect();
    const rel = ((ev.clientX - caja.left) / caja.width) * AN;
    let i = Math.round(((rel - M.izda) / anU) * (dias.length - 1));
    i = Math.max(0, Math.min(dias.length - 1, i));
    const dia = dias[i];

    guia.setAttribute('x1', x(i));
    guia.setAttribute('x2', x(i));
    guia.setAttribute('opacity', 1);

    globo.replaceChildren();
    globo.append(crear('b', null, `${dia.dia} ${dia.fecha}`));
    const filas = dia.conversaciones
      ? [[`${dia.conversaciones} conversaciones`, ''],
         [`${dia.resueltas} resueltas`, 'ok'],
         [`${dia.escaladas} a tu mesa`, 'av'],
         [dia.ms_mediana === null ? 'sin tiempos' : `mediana ${dia.ms_mediana} ms`, '']]
      : [['cerrado', '']];
    filas.forEach(([txt, clase]) => globo.append(crear('span', clase, txt)));
    globo.hidden = false;
    globo.style.left = `${(x(i) / AN) * 100}%`;
  };
  const salir = () => { globo.hidden = true; guia.setAttribute('opacity', 0); };

  svg.addEventListener('pointermove', mover);
  svg.addEventListener('pointerleave', salir);

  destino.replaceChildren(envoltorio);

  // El trazo se dibuja solo al entrar. Con movimiento reducido, ya dibujado.
  if (!sinMovimiento()) {
    const largo = linea.getTotalLength();
    linea.style.strokeDasharray = largo;
    linea.style.strokeDashoffset = largo;
    linea.getBoundingClientRect();           // fuerza el reflow antes de animar
    linea.style.transition = 'stroke-dashoffset 900ms cubic-bezier(.22,.8,.3,1)';
    linea.style.strokeDashoffset = '0';
  }
}

/* ========================================================== los anillos */
function anillo(valor, etiqueta, pie, color) {
  const R = 52, C = 2 * Math.PI * R;
  const caja = crear('div', 'anillo');
  const svg = svgEl('svg', {
    viewBox: '0 0 130 130', role: 'img',
    'aria-label': `${etiqueta}: ${(valor * 100).toFixed(1)}%`,
  });
  svg.append(svgEl('circle', {
    cx: 65, cy: 65, r: R, fill: 'none',
    stroke: 'var(--anillo-fondo)', 'stroke-width': 11,
  }));
  const arco = svgEl('circle', {
    cx: 65, cy: 65, r: R, fill: 'none', stroke: color, 'stroke-width': 11,
    'stroke-linecap': 'round', transform: 'rotate(-90 65 65)',
    'stroke-dasharray': C, 'stroke-dashoffset': sinMovimiento()
      ? C * (1 - valor) : C,
  });
  svg.append(arco);

  const num = svgEl('text', {x: 65, y: 68, 'text-anchor': 'middle', class: 'anillo-num'});
  num.textContent = (valor * 100).toFixed(1).replace('.', ',') + '%';
  const sub = svgEl('text', {x: 65, y: 86, 'text-anchor': 'middle', class: 'anillo-sub'});
  sub.textContent = pie;
  svg.append(num, sub);

  caja.append(svg, crear('p', 'anillo-eti', etiqueta));

  if (!sinMovimiento()) {
    requestAnimationFrame(() => {
      arco.style.transition = 'stroke-dashoffset 950ms cubic-bezier(.22,.8,.3,1)';
      arco.setAttribute('stroke-dashoffset', C * (1 - valor));
    });
  }
  return caja;
}

/* ============================================================ el gauge
   Semicircular, con UNA medida real y su nombre. No es un "índice de salud":
   ese número no existe en ningún fichero y habría que inventarlo. */
function pintarGauge(valor, titulo, pie) {
  const destino = $('#gauge');
  if (!destino) return;
  const R = 78, cx = 100, cy = 100;
  const largo = Math.PI * R;                    // media circunferencia

  const svg = svgEl('svg', {
    viewBox: '0 0 200 124', class: 'gauge', role: 'img',
    'aria-label': `${titulo}: ${(valor * 100).toFixed(1)}%`,
  });
  const arcoD = `M ${cx - R} ${cy} A ${R} ${R} 0 0 1 ${cx + R} ${cy}`;
  svg.append(svgEl('path', {
    d: arcoD, fill: 'none', stroke: 'var(--anillo-fondo)',
    'stroke-width': 15, 'stroke-linecap': 'round',
  }));
  const arco = svgEl('path', {
    d: arcoD, fill: 'none', stroke: 'var(--cian)', 'stroke-width': 15,
    'stroke-linecap': 'round',
    'stroke-dasharray': largo,
    'stroke-dashoffset': sinMovimiento() ? largo * (1 - valor) : largo,
  });
  svg.append(arco);

  const num = svgEl('text', {x: cx, y: cy - 12, 'text-anchor': 'middle', class: 'gauge-num'});
  num.textContent = (valor * 100).toFixed(1).replace('.', ',') + '%';
  svg.append(num);

  destino.replaceChildren(svg,
                          crear('p', 'gauge-eti', titulo),
                          crear('p', 'gauge-pie', pie));

  if (!sinMovimiento()) {
    requestAnimationFrame(() => {
      arco.style.transition = 'stroke-dashoffset 1s cubic-bezier(.22,.8,.3,1)';
      arco.setAttribute('stroke-dashoffset', largo * (1 - valor));
    });
  }
}

/* ============================== la barra más alta, destacada en acento */
/* Las listas ya vienen ordenadas de mayor a menor desde actividad.js, así que
   la primera es la mayor. Se marca con una clase y el color lo pone el CSS:
   aquí no se repinta nada, solo se señala cuál manda. */
function destacarBarras() {
  ['#g-intenciones', '#g-motivos', '#g-atasco'].forEach((sel) => {
    const zona = document.querySelector(sel);
    if (!zona) return;
    // Se vuelve a mirar en cada pasada porque actividad.js puede repintar la
    // lista después (al refrescar), y entonces la clase se habría perdido.
    const primera = zona.querySelector('.barra');
    if (primera && !primera.classList.contains('manda')) {
      zona.querySelectorAll('.barra.manda').forEach((b) => b.classList.remove('manda'));
      primera.classList.add('manda');
    }
  });
}

/* ================================================================ arranque */
(async () => {
  let act = null, est = null;
  try { act = await api('/api/actividad'); } catch (e) { /* sin serie */ }
  try { est = await api('/api/estado'); } catch (e) { /* sin calidad */ }

  if (act && Array.isArray(act.por_dia) && act.por_dia.length > 1) {
    // Se espera a que actividad.js haya pintado lo suyo para sustituirlo: si
    // se adelantara, su replaceChildren() borraría el área recién puesta.
    //
    // CON TOPE. Sin él, si actividad.js no llegara a pintar nunca —su fetch
    // falla, o alguien renombra el hueco— esto se quedaría despertando cada
    // 120 ms para siempre, gastando batería sin que nadie lo note.
    // Se busca EXACTAMENTE lo que pinta actividad.js (.g-barras-v) y no "¿tiene
    // hijos?". Con esa comprobación floja, el esqueleto que mete ui.js contaba
    // como contenido: el área se dibujaba encima del esqueleto y acto seguido
    // actividad.js la borraba al pintar sus barras.
    let intentos = 0;
    const esperar = () => {
      const hueco = $('#g-dias');
      if (hueco && hueco.querySelector('.g-barras-v')) {
        pintarArea(act.por_dia);
        return;
      }
      if (++intentos < 50) setTimeout(esperar, 120);   // 6 s y se rinde
    };
    esperar();
  }

  const c = est && est.calidad_medida;
  const r = act && act.resumen;

  if (r && typeof r.tasa_resolucion === 'number') {
    pintarGauge(r.tasa_resolucion, 'Resueltas sin una persona',
                `${r.resueltas_sin_persona} de ${r.conversaciones} conversaciones · `
                + `${r.escaladas} llegaron a tu mesa`);
  } else if ($('#gauge')) {
    $('#gauge').replaceChildren(crear('p', 'vacio',
      'Sin medir. Ejecuta 10_simular.py para tener siete días de tráfico.'));
  }

  const destino = $('#anillos');
  if (destino) {
    const fichas = c ? [
      [c.guardarrail, 'Guardarraíl de precios',
       `${c.piezas_inexistentes_probadas} de ${c.piezas_inexistentes_probadas}`,
       'var(--cat-1)'],
      [c.acierto_ahora, 'Acierto a la primera',
       `${c.preguntas_banco} preguntas`, 'var(--cat-2)'],
      [c.acierto_top3, 'Acierto en el top 3',
       `${c.preguntas_banco} preguntas`, 'var(--cat-3)'],
    ].filter(([v]) => typeof v === 'number') : [];

    if (fichas.length) {
      destino.replaceChildren(...fichas.map((f) => anillo(...f)));
    } else {
      destino.replaceChildren(crear('p', 'vacio',
        'Sin medir. Ejecuta tests/test_busqueda.py y luego 05_panel_datos.py.'));
    }
  }

  // Varias pasadas y no una sola a los 400 ms: actividad.js pinta cuando le
  // llega su fetch, y en una máquina lenta a los 400 ms aún no hay barras.
  [400, 1200, 3000].forEach((ms) => setTimeout(destacarBarras, ms));
})();
