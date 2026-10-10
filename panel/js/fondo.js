/* Fondo en movimiento del centro de control.
   Una malla de nodos que se desplazan despacio y se enlazan cuando están cerca:
   evoca un catálogo vivo donde las piezas se relacionan entre sí, que es
   literalmente lo que hace el buscador por debajo. Con ratón, el puntero
   también se enlaza con los nodos que tiene cerca.

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
  let ancho, alto, nodos = [], raf = null, puntero = null;

  function dimensionar() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    ancho = lienzo.clientWidth;
    alto = lienzo.clientHeight;
    lienzo.width = ancho * dpr;
    lienzo.height = alto * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Densidad proporcional a la superficie, con techo para portátiles modestos.
    const cuantos = Math.min(90, Math.round((ancho * alto) / 16000));
    // A 0,16 px por fotograma el movimiento no se llegaba a ver; a 0,5 se nota
    // que la malla vive y sigue siendo lenta (unos 15 px por segundo).
    nodos = Array.from({length: cuantos}, () => ({
      x: Math.random() * ancho,
      y: Math.random() * alto,
      vx: (Math.random() - 0.5) * 0.5,
      vy: (Math.random() - 0.5) * 0.5,
      r: Math.random() * 1.5 + 0.8,
    }));
  }

  const ENLACE = 165;                       // px: a más distancia, sin línea
  const RATON = 180;                        // px: alcance de las líneas al puntero

  function pintar() {
    ctx.clearRect(0, 0, ancho, alto);
    ctx.lineWidth = 0.7;

    // Enlaces primero, para que los nodos queden por encima.
    for (let i = 0; i < nodos.length; i++) {
      for (let j = i + 1; j < nodos.length; j++) {
        const dx = nodos[i].x - nodos[j].x, dy = nodos[i].y - nodos[j].y;
        const d2 = dx * dx + dy * dy;
        if (d2 > ENLACE * ENLACE) continue;
        const alfa = (1 - Math.sqrt(d2) / ENLACE) * 0.32;
        ctx.strokeStyle = `rgba(${acento},${alfa})`;
        ctx.beginPath();
        ctx.moveTo(nodos[i].x, nodos[i].y);
        ctx.lineTo(nodos[j].x, nodos[j].y);
        ctx.stroke();
      }
    }
    // El puntero también enlaza: tira líneas a los nodos que tiene cerca. Es
    // el único gesto de la malla, y solo dibuja: no empuja ni atrae nada.
    if (puntero) {
      for (const n of nodos) {
        const dx = n.x - puntero.x, dy = n.y - puntero.y;
        const d2 = dx * dx + dy * dy;
        if (d2 > RATON * RATON) continue;
        ctx.strokeStyle = `rgba(${acento},${(1 - Math.sqrt(d2) / RATON) * 0.42})`;
        ctx.beginPath();
        ctx.moveTo(puntero.x, puntero.y);
        ctx.lineTo(n.x, n.y);
        ctx.stroke();
      }
    }
    ctx.fillStyle = `rgba(${acento},0.7)`;
    for (const n of nodos) {
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

  // El puntero, en coordenadas de la ventana: el lienzo es fijo y la ocupa
  // entera. Solo el ratón; en táctil no hay puntero que seguir.
  window.addEventListener('pointermove', (e) => {
    if (e.pointerType === 'mouse') puntero = {x: e.clientX, y: e.clientY};
  }, {passive: true});
  document.documentElement.addEventListener('mouseleave', () => { puntero = null; });
  window.addEventListener('blur', () => { puntero = null; });

  arrancar();
})();
