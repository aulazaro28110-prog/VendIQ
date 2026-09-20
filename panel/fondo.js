/* Fondo en movimiento del centro de control.
   Una malla de nodos que se desplazan despacio y se enlazan cuando están cerca:
   evoca un catálogo vivo donde las piezas se relacionan entre sí, que es
   literalmente lo que hace el buscador por debajo.

   Se dibuja en canvas y no en SVG porque son cientos de líneas recalculadas en cada
   fotograma; con nodos del DOM el navegador se ahogaría.
   Respeta prefers-reduced-motion: si el usuario lo pide, pinta una sola vez y para. */

(() => {
  const lienzo = document.getElementById('fondo');
  if (!lienzo) return;
  const ctx = lienzo.getContext('2d');
  const quieto = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* El color NO se escribe aqui. Se lee de --accent, que es el token del
     sistema, para que la malla siga al tema sin tener el teal apuntado en dos
     sitios: antes era '26,161,151' a pelo, el acento de antes del reskin, y
     al cambiar la paleta se quedo pintando un color que ya no existia. */
  function leerAcento() {
    const v = getComputedStyle(document.documentElement)
      .getPropertyValue('--accent').trim();
    const m = v.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (!m) return '45,212,191';                 // el teal oscuro, de reserva
    let h = m[1];
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).join(',');
  }

  let acento = leerAcento();
  let ancho, alto, nodos = [], raf = null;

  function dimensionar() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    ancho = lienzo.clientWidth;
    alto = lienzo.clientHeight;
    lienzo.width = ancho * dpr;
    lienzo.height = alto * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Densidad proporcional a la superficie, con techo para portátiles modestos.
    const cuantos = Math.min(90, Math.round((ancho * alto) / 16000));
    nodos = Array.from({length: cuantos}, () => ({
      x: Math.random() * ancho,
      y: Math.random() * alto,
      vx: (Math.random() - 0.5) * 0.16,
      vy: (Math.random() - 0.5) * 0.16,
      r: Math.random() * 1.4 + 0.7,
    }));
  }

  function pintar() {
    ctx.clearRect(0, 0, ancho, alto);

    // Enlaces primero, para que los nodos queden por encima.
    for (let i = 0; i < nodos.length; i++) {
      for (let j = i + 1; j < nodos.length; j++) {
        const dx = nodos[i].x - nodos[j].x, dy = nodos[i].y - nodos[j].y;
        const d2 = dx * dx + dy * dy;
        if (d2 > 20000) continue;                    // 141 px
        const alfa = (1 - Math.sqrt(d2) / 141) * 0.16;
        ctx.strokeStyle = `rgba(${acento},${alfa})`;
        ctx.lineWidth = 0.6;
        ctx.beginPath();
        ctx.moveTo(nodos[i].x, nodos[i].y);
        ctx.lineTo(nodos[j].x, nodos[j].y);
        ctx.stroke();
      }
    }
    for (const n of nodos) {
      ctx.fillStyle = `rgba(${acento},0.5)`;
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function avanzar() {
    for (const n of nodos) {
      n.x += n.vx; n.y += n.vy;
      if (n.x < -20) n.x = ancho + 20;
      if (n.x > ancho + 20) n.x = -20;
      if (n.y < -20) n.y = alto + 20;
      if (n.y > alto + 20) n.y = -20;
    }
    pintar();
    raf = requestAnimationFrame(avanzar);
  }

  function arrancar() {
    if (raf) cancelAnimationFrame(raf);
    dimensionar();
    if (quieto) { pintar(); return; }
    avanzar();
  }

  let temporizador;
  window.addEventListener('resize', () => {
    clearTimeout(temporizador);
    temporizador = setTimeout(arrancar, 200);
  });

  // Si la pestaña no se ve, no se gasta batería en animarla.
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { if (raf) cancelAnimationFrame(raf); raf = null; }
    else if (!quieto && !raf) avanzar();
  });

  /* Al cambiar de tema hay que volver a leer el acento: en claro es otro teal,
     mas oscuro, porque el de modo oscuro sobre blanco no se ve. Con
     movimiento reducido no hay bucle que lo repinte solo, asi que se fuerza
     un pintado. */
  new MutationObserver(() => {
    const nuevo = leerAcento();
    if (nuevo === acento) return;
    acento = nuevo;
    if (quieto) pintar();
  }).observe(document.documentElement, {
    attributes: true, attributeFilter: ['data-tema'],
  });

  arrancar();
})();
