/* VendIQ · barra superior, migas y paleta de comandos (⌘K)
   ========================================================================
   Tres cosas que van juntas porque las tres contestan a lo mismo: "dónde
   estoy y cómo llego a lo que busco" en una página que mide nueve secciones
   y baja mucho.

     · la barra de arriba, con las migas y el disparador de búsqueda
     · las migas, que dicen en qué grupo y en qué sección estás
     · la paleta, que salta a una sección o BUSCA EN EL STOCK DE VERDAD

   ADITIVO, como todo lo demás. Este fichero no reescribe nada: lee el menú
   que ya existe, usa `api()` y `consultar()` de panel.js tal cual, y se monta
   en huecos nuevos. Si falla o no carga, no se pierde ni una función: el menú
   lateral sigue navegando y el buscador de la sección "Buscar en el stock"
   sigue estando entero.

   DE DÓNDE SALE EL ÍNDICE DE SECCIONES
   ------------------------------------
   Del propio menú lateral, leyendo sus <a href="#..."> y las cabeceras de
   grupo. No hay una segunda lista escrita a mano: si mañana se añade una
   sección al menú, aparece sola en la paleta y en las migas. Dos listas que
   hay que acordarse de mantener a la vez es como se desincronizan.

   LOS RESULTADOS DE STOCK SON REALES
   ----------------------------------
   Salen de /api/consultar, el mismo endpoint que usa el buscador de la
   página, con la misma pregunta. Se filtran a `tipo === 'inventario'`, que es
   lo que de verdad es una pieza del almacén; lo demás que devuelve el motor
   son documentos de política, y colarlos aquí como si fueran stock sería
   justo el tipo de mentira que este panel no se puede permitir. Si la
   petición falla, ese grupo lo dice y el de secciones sigue funcionando. */

(() => {
  'use strict';

  const ATAJO = navigator.platform.toLowerCase().includes('mac') ? '⌘' : 'Ctrl';

  /* ------------------------------------------------ índice de secciones */
  /* Recorre el menú EN ORDEN. Cada cabecera de grupo que se encuentra pasa a
     ser el grupo de los enlaces que vienen detrás, que es exactamente cómo
     está escrito el HTML. */
  function leerSecciones() {
    const caja = document.querySelector('nav.barra .barra-enlaces');
    if (!caja) return [];
    const lista = [];
    let grupo = '';
    [...caja.children].forEach((nodo) => {
      if (nodo.classList.contains('nav-grupo')) {
        grupo = nodo.textContent.trim();
        return;
      }
      if (nodo.tagName !== 'A') return;
      const etiqueta = nodo.querySelector('span');
      lista.push({
        href: nodo.getAttribute('href') || '',
        titulo: (etiqueta ? etiqueta.textContent : nodo.textContent).trim(),
        grupo,
      });
    });
    return lista;
  }

  const SECCIONES = leerSecciones();
  if (!SECCIONES.length) return;        // sin menú no hay nada que montar

  const porHref = new Map(SECCIONES.map((s) => [s.href, s]));

  /* Si el sistema pide menos movimiento, el salto es seco. `scroll-behavior`
     en CSS no vale aquí: un scrollIntoView con behavior:'smooth' escrito a
     mano se anima igual, y quien ha pedido no marearse se marea. */
  const suave = () => (window.matchMedia
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ? 'auto' : 'smooth');

  /* Sin acentos y en minúsculas, para que "seccion" encuentre "sección". */
  const plano = (t) => t.toLowerCase().normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');

  /* ------------------------------------------------------- la barra ---- */
  function lupa(clase) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('class', clase);
    svg.setAttribute('aria-hidden', 'true');
    const c = document.createElementNS(ns, 'circle');
    c.setAttribute('cx', '11'); c.setAttribute('cy', '11'); c.setAttribute('r', '7');
    const l = document.createElementNS(ns, 'path');
    l.setAttribute('d', 'M20 20l-3.9-3.9');
    svg.append(c, l);
    return svg;
  }

  const miga = crear('nav', 'miga');
  miga.setAttribute('aria-label', 'Dónde estás');

  const disparador = crear('button', 'chrome-buscar');
  disparador.type = 'button';
  disparador.setAttribute('aria-keyshortcuts', 'Control+K Meta+K');
  disparador.append(
    lupa('chrome-lupa'),
    crear('span', 'chrome-txt', 'Buscar una pieza o ir a una sección'),
    crear('kbd', null, ATAJO),
    crear('kbd', null, 'K'));

  const chrome = crear('div', 'envoltorio chrome');
  chrome.append(miga, disparador);
  const franja = crear('div', 'chrome-franja');
  franja.append(chrome);

  const cabecera = document.querySelector('header.top');
  if (cabecera && cabecera.parentNode) {
    cabecera.parentNode.insertBefore(franja, cabecera);
  }

  /* --------------------------------------------------------- las migas */
  /* No hay un segundo observador de scroll: tema.js ya marca con .aqui el
     enlace de la sección en la que estás. Aquí solo se mira ESE cambio. */
  function pintarMiga() {
    const activo = document.querySelector('nav.barra .barra-enlaces a.aqui');
    const s = activo ? porHref.get(activo.getAttribute('href')) : null;
    const trozos = ['VendIQ'];
    if (s) {
      if (s.grupo) trozos.push(s.grupo);
      trozos.push(s.titulo);
    }
    miga.replaceChildren(...trozos.flatMap((t, i) => {
      const nodos = i ? [crear('span', 'miga-sep', '/')] : [];
      nodos.push(crear(i === trozos.length - 1 && trozos.length > 1 ? 'b' : 'span',
                       'miga-paso', t));
      return nodos;
    }));
  }
  pintarMiga();
  const caja = document.querySelector('nav.barra .barra-enlaces');
  if (caja) {
    new MutationObserver(pintarMiga).observe(caja, {
      subtree: true, attributes: true, attributeFilter: ['class'],
    });
  }

  /* ------------------------------------------------------- la paleta --- */
  const velo = crear('div', 'pal-velo');
  velo.hidden = true;

  const entrada = document.createElement('input');
  entrada.type = 'text';
  entrada.className = 'pal-entrada';
  entrada.autocomplete = 'off';
  entrada.spellcheck = false;
  entrada.placeholder = 'Busca una pieza del stock, o escribe para ir a una sección';
  entrada.setAttribute('aria-label', 'Buscar');
  entrada.setAttribute('role', 'combobox');
  entrada.setAttribute('aria-expanded', 'true');
  entrada.setAttribute('aria-controls', 'pal-lista');

  const campo = crear('div', 'pal-campo');
  campo.append(lupa('pal-lupa'), entrada, crear('kbd', null, 'Esc'));

  const lista = crear('div', 'pal-lista');
  lista.id = 'pal-lista';
  lista.setAttribute('role', 'listbox');

  const pie = crear('div', 'pal-pie');
  pie.append(crear('span', null, '↑↓ moverse'), crear('span', null, '↵ abrir'),
             crear('span', null, 'Esc cerrar'));

  const paleta = crear('div', 'pal');
  paleta.setAttribute('role', 'dialog');
  paleta.setAttribute('aria-modal', 'true');
  paleta.setAttribute('aria-label', 'Buscar o ir a');
  paleta.hidden = true;
  paleta.append(campo, lista, pie);

  document.body.append(velo, paleta);

  /* --------------------------------------------------------- estado --- */
  let opciones = [];          // [{tipo, titulo, pie, dcha, accion}]
  let elegida = 0;
  let quienDevolvio = null;   // a quién le devolvemos el foco al cerrar
  let temporizador = null;
  let turno = 0;              // para descartar respuestas que llegan tarde

  const filaHTML = (op, i) => {
    const f = crear('div', 'pal-fila' + (i === elegida ? ' sel' : ''));
    f.id = 'pal-op-' + i;
    f.setAttribute('role', 'option');
    f.setAttribute('aria-selected', i === elegida ? 'true' : 'false');

    const izda = crear('div', 'pal-txt');
    izda.append(crear('span', 'pal-titulo', op.titulo));
    if (op.pie) izda.append(crear('span', 'pal-pie-fila', op.pie));
    f.append(izda);
    if (op.dcha) f.append(crear('span', 'pal-dcha', op.dcha));

    f.onmouseenter = () => { elegida = i; marcar(); };
    f.onclick = () => lanzar(i);
    return f;
  };

  /* Solo repinta la marca de la elegida. Redibujar la lista entera en cada
     flecha hace que el ratón por encima robe la selección y da saltos. */
  function marcar() {
    [...lista.querySelectorAll('.pal-fila')].forEach((f, i) => {
      const es = i === elegida;
      f.classList.toggle('sel', es);
      f.setAttribute('aria-selected', es ? 'true' : 'false');
      if (es) {
        entrada.setAttribute('aria-activedescendant', f.id);
        f.scrollIntoView({block: 'nearest'});
      }
    });
  }

  /* El índice de cada fila tiene que ser su posición en `opciones`, que es
     por donde se mueven las flechas: por eso se construyen a la vez y no en
     dos pasadas. Las cabeceras de grupo y los avisos NO cuentan como opción,
     que si no las flechas se paran en sitios donde no hay nada que abrir. */
  function pintar(grupos) {
    opciones = [];
    const salida = [];
    grupos.forEach(({nombre, filas, aviso}) => {
      if (!filas.length && !aviso) return;
      salida.push(crear('p', 'pal-grupo', nombre));
      if (aviso) salida.push(crear('p', 'pal-aviso', aviso));
      filas.forEach((op) => salida.push(filaHTML(op, opciones.push(op) - 1)));
    });
    if (!salida.length) {
      salida.push(crear('p', 'pal-aviso',
        'Nada que coincida. Prueba con la pieza y el coche: ' +
        '"alternador BMW Serie 1".'));
    }
    if (elegida >= opciones.length) elegida = 0;
    lista.replaceChildren(...salida);
    marcar();
  }

  function lanzar(i) {
    const op = opciones[i];
    if (!op) return;
    cerrar();
    op.accion();
  }

  /* --------------------------------------------------------- búsqueda -- */
  function seccionesQueCuadran(q) {
    const t = plano(q);
    return SECCIONES
      .filter((s) => !t || plano(s.titulo).includes(t) || plano(s.grupo).includes(t))
      .map((s) => ({
        titulo: s.titulo,
        pie: s.grupo,
        dcha: 'Ir',
        accion: () => {
          const destino = document.querySelector(s.href);
          if (destino) destino.scrollIntoView({behavior: suave(), block: 'start'});
          else location.hash = s.href;
        },
      }));
  }

  function filaDeStock(r) {
    const m = r.meta || {};
    const coche = [m.marca, m.modelo, m.motor].filter(Boolean).join(' ');
    return {
      titulo: m.pieza || (r.texto || '').slice(0, 60),
      pie: [coche, m.anio && '(' + m.anio + ')', m.disponibilidad]
        .filter(Boolean).join(' · '),
      dcha: m.precio || r.precio || '',
      accion: () => {
        // Se manda a la sección del buscador con la pregunta puesta, en vez
        // de enseñar aquí media ficha: allí está la ficha entera, con su
        // puntuación, su decisión y su porqué.
        const campoBusqueda = document.querySelector('#entrada');
        const texto = [m.pieza, coche].filter(Boolean).join(' ');
        if (campoBusqueda) campoBusqueda.value = texto;
        const destino = document.querySelector('#stock');
        if (destino) destino.scrollIntoView({behavior: suave(), block: 'start'});
        if (typeof consultar === 'function') consultar(texto);
      },
    };
  }

  async function buscar(q) {
    const mio = ++turno;
    const grupos = [{nombre: 'Ir a', filas: seccionesQueCuadran(q)}];

    if (q.trim().length < 3) {
      grupos.push({nombre: 'Stock', filas: [],
                   aviso: 'Escribe tres letras o más para buscar en el almacén.'});
      pintar(grupos);
      return;
    }

    pintar(grupos.concat({nombre: 'Stock', filas: [], aviso: 'Buscando…'}));

    let piezas = [];
    let aviso = null;
    try {
      const d = await api('/api/consultar', {pregunta: q});
      piezas = (d.resultados || []).filter((r) => r.tipo === 'inventario');
      if (!piezas.length) aviso = 'Ninguna pieza del almacén cuadra con eso.';
    } catch (e) {
      aviso = 'No se pudo consultar el almacén: ' + e.message;
    }
    if (mio !== turno) return;          // llegó tarde; ya hay otra búsqueda
    pintar(grupos.concat({
      nombre: 'Stock', filas: piezas.slice(0, 6).map(filaDeStock), aviso,
    }));
  }

  /* ------------------------------------------------------ abrir/cerrar - */
  function abrir() {
    if (!paleta.hidden) return;
    quienDevolvio = document.activeElement;
    paleta.hidden = false;
    velo.hidden = false;
    entrada.value = '';
    elegida = 0;
    buscar('');
    entrada.focus();
  }

  function cerrar() {
    if (paleta.hidden) return;
    paleta.hidden = true;
    velo.hidden = true;
    clearTimeout(temporizador);
    turno++;                            // invalida cualquier búsqueda en vuelo
    // preventScroll es obligatorio aqui: devolver el foco al disparador,
    // que esta arriba del todo, arrastraba la pagina hasta el con el
    // navegador, justo antes de que la accion la llevara a su destino.
    if (quienDevolvio && quienDevolvio.focus) {
      quienDevolvio.focus({preventScroll: true});
    }
  }

  disparador.onclick = abrir;
  velo.onclick = cerrar;

  entrada.oninput = () => {
    clearTimeout(temporizador);
    const q = entrada.value;
    elegida = 0;
    // Las secciones se filtran al instante; el almacén, con freno, para no
    // lanzarle una consulta al motor por cada tecla.
    temporizador = setTimeout(() => buscar(q), 180);
  };

  entrada.onkeydown = (ev) => {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      if (!opciones.length) return;
      elegida = (elegida + (ev.key === 'ArrowDown' ? 1 : -1) + opciones.length)
                % opciones.length;
      marcar();
    } else if (ev.key === 'Enter') {
      ev.preventDefault();
      lanzar(elegida);
    } else if (ev.key === 'Escape') {
      ev.preventDefault();
      cerrar();
    } else if (ev.key === 'Tab') {
      ev.preventDefault();             // el foco no se escapa del diálogo
    }
  };

  document.addEventListener('keydown', (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'k' || ev.key === 'K')) {
      ev.preventDefault();
      if (paleta.hidden) abrir(); else cerrar();
    } else if (ev.key === 'Escape' && !paleta.hidden) {
      cerrar();
    }
  });
})();
