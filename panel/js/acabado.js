/* VendIQ · capa de acabado, el comportamiento
   ========================================================================
   Lo único de la capa de acabado que necesita JavaScript. Nada de ello pinta un
   dato ni pide nada al servidor:

     · plegar la barra lateral a un carril de 60 px (escritorio, se recuerda)
     · abrirla como cajón con velo en móvil: Escape, clic fuera o elegir
       destino la cierran, y mientras está abierta lo de detrás queda inerte
     · las entradas suaves al hacer scroll (el ".appear" del encargo)

   ADITIVO, como barra.js: construye encima de la .sb que aquel ya montó y no
   reescribe nada. Si este fichero no cargara, la barra se queda desplegada en
   escritorio, el móvil conserva su barra de arriba de siempre y todo el
   contenido se ve desde el principio, quieto. */
(() => {
  'use strict';
  const raiz = document.documentElement;
  const ESTRECHO = window.matchMedia('(max-width: 959px)');
  const QUIETO = window.matchMedia('(prefers-reduced-motion: reduce)');
  const CLAVE = 'vendiq-sb-plegada';   // la misma que lee el <script> del <head>

  // Envuelto: con el almacenamiento bloqueado, localStorage LANZA en vez de
  // devolver null, y una barra que revienta por no recordarse es peor que
  // una que no se recuerda.
  const leer = () => { try { return localStorage.getItem(CLAVE) === '1'; } catch (e) { return false; } };
  const guardar = (si) => { try { localStorage.setItem(CLAVE, si ? '1' : '0'); } catch (e) { /* da igual */ } };

  /* ─────────────────────────────────── la barra: plegar y cajón ─── */
  function montarBarra() {
    const sb = document.querySelector('.sb');
    if (!sb || !raiz.classList.contains('shell')) return;   // barra.js no montó

    // La fila de arriba: la marca que ya puso barra.js, más la hamburguesa.
    const cab = document.createElement('div');
    cab.className = 'sb-cab';
    const marca = sb.querySelector(':scope > .marca');
    if (marca) cab.append(marca);
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.className = 'sb-alternar';
    for (let i = 0; i < 3; i++) boton.append(document.createElement('i'));
    cab.append(boton);
    sb.prepend(cab);

    // En el carril el nombre se esconde a la vista, pero sigue ahí para el
    // lector de pantalla; el title se lo enseña al ratón.
    sb.querySelectorAll('.sb-links a').forEach((a) => {
      const s = a.querySelector('span');
      if (s && !a.title) a.title = s.textContent.trim();
    });

    // El «en vivo» vivía en la barra de arriba, que en móvil desaparece. Se
    // muda al pie de la lateral: el mismo nodo con el mismo id, así que
    // panel.js lo sigue actualizando sin enterarse.
    const vivo = document.querySelector('nav.barra .estado-vivo');
    const pie = sb.querySelector('.sb-pie');
    if (vivo && pie) pie.prepend(vivo);

    const velo = document.createElement('div');
    velo.className = 'sb-velo';
    velo.setAttribute('aria-hidden', 'true');
    document.body.append(velo);

    let plegada = leer();
    let abierta = false;
    let quien = null;              // a quién devolverle el foco al cerrar

    // Con el cajón abierto, lo de detrás no se toca ni se tabula: es lo que
    // lo hace un modal de verdad y no una caja pintada encima.
    const detras = () => ['main', 'header.top', '.chrome-franja', '.saltar']
      .map((s) => document.querySelector(s)).filter(Boolean);

    function pintar() {
      const movil = ESTRECHO.matches;
      if (!movil) abierta = false;          // al ensanchar, el cajón se cierra solo
      raiz.classList.toggle('sb-plegada', plegada);
      raiz.classList.toggle('sb-abierta', abierta);
      raiz.classList.toggle('sb-carril', movil ? !abierta : plegada);
      detras().forEach((n) => { n.inert = abierta; });
      boton.setAttribute('aria-expanded', String(movil ? abierta : !plegada));
      boton.setAttribute('aria-label', movil
        ? (abierta ? 'Cerrar el menú' : 'Abrir el menú')
        : (plegada ? 'Desplegar el menú' : 'Plegar el menú'));
    }

    // Al abrir, el foco se queda en la hamburguesa, que ya está DENTRO del
    // cajón y ahora es su botón de cerrar.
    function abrir() {
      quien = document.activeElement;
      abierta = true;
      pintar();
    }
    function cerrar(devolverFoco) {
      if (!abierta) return;
      abierta = false;
      pintar();
      if (devolverFoco && quien && quien.focus) quien.focus({preventScroll: true});
    }

    boton.addEventListener('click', () => {
      if (ESTRECHO.matches) { if (abierta) cerrar(true); else abrir(); return; }
      plegada = !plegada;
      guardar(plegada);
      pintar();
    });
    velo.addEventListener('click', () => cerrar(true));
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape' && abierta) cerrar(true);
    });
    // Elegir destino cierra el cajón. El salto lo sigue haciendo el ancla de
    // siempre, y por eso NO se devuelve el foco: arrastraría la página.
    sb.addEventListener('click', (ev) => {
      if (abierta && ev.target.closest('.sb-links a')) cerrar(false);
    });
    ESTRECHO.addEventListener('change', pintar);

    pintar();
    raiz.classList.add('v-listo');
  }

  /* ──────────────────────────────── las entradas al hacer scroll ─── */
  /* Nunca se esconde nada a ciegas (ver ui.js): solo lo que al cargar queda
     por DEBAJO de la primera pantalla, y solo si hay IntersectionObserver,
     que es lo que garantiza que se va a destapar en cuanto asome. */
  function montarEntradas() {
    if (QUIETO.matches || !('IntersectionObserver' in window)) return;
    const GRUPOS = [
      ['.bloque > .eyebrow, .bloque > h2, .bloque > .intro, .bloque > .sub-titulo', 'apa-soft'],
      ['.indicadores > .ind, .stats > div', 'apa-pop'],
      ['.carta, .hito, .aviso-escala, .declaracion, .chat-mandos, .chat-rejilla, .outlook',
       'apa-scale'],
    ];
    const alto = window.innerHeight * 1.2;   // ui.js anima hasta 1,15: sin solaparse

    const vigia = new IntersectionObserver((entradas) => {
      entradas.filter((e) => e.isIntersecting).map((e) => e.target)
        .sort((a, b) => (a.compareDocumentPosition(b)
          & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1)
        .forEach((el, i) => {
          el.style.setProperty('--apa-d', Math.min(i, 6) * 70 + 'ms');
          el.classList.add('apa-vista');
          vigia.unobserve(el);
        });
    });

    GRUPOS.forEach(([selector, clase]) => {
      document.querySelectorAll(selector).forEach((el) => {
        if (el.classList.contains('entra') || el.closest('.apa')) return;
        if (clase === 'apa-pop' && el.closest('.carta')) return;   // ya entra su tarjeta
        // Lo que vive en un <details> plegado no se ve hasta que alguien lo
        // abre: esconderlo a la espera de un scroll sería arriesgarse a que
        // aparezca vacío al desplegarlo.
        if (el.closest('details')) return;
        if (el.getBoundingClientRect().top < alto) return;         // la primera pantalla, no
        el.classList.add('apa', clase);
        vigia.observe(el);
      });
    });
    raiz.classList.add('v-aparece');
  }

  /* ════════════════════════════════════════════════════════ arranque */
  montarBarra();
  // Después de ui.js: su escalonado marca la primera pantalla en
  // DOMContentLoaded y estas entradas tienen que saber cuáles ya animan.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', montarEntradas);
  } else {
    montarEntradas();
  }
})();
