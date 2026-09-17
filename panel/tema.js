/* VendIQ · tema y navegación
   ------------------------------------------------------------------------
   Dos cosas pequeñas y aditivas: el interruptor claro/oscuro y el resaltado
   del enlace de la sección que se está mirando. Ninguna toca datos ni pide
   nada al servidor.

   El tema se guarda en localStorage. Si el navegador lo tiene bloqueado
   (ventana privada, cookies capadas) el acceso LANZA, no devuelve null, así
   que va envuelto: un panel que revienta por no poder recordar un color
   sería un panel peor que uno que no recuerda el color. */

const TEMA_CLAVE = 'vendiq-tema';

function leerTema() {
  try {
    const guardado = localStorage.getItem(TEMA_CLAVE);
    if (guardado === 'claro' || guardado === 'oscuro') return guardado;
  } catch (e) { /* sin almacenamiento: se decide por el sistema */ }
  return window.matchMedia
    && window.matchMedia('(prefers-color-scheme: light)').matches
    ? 'claro' : 'oscuro';
}

function aplicarTema(tema) {
  document.documentElement.dataset.tema = tema;
  const bt = document.querySelector('.tema-toggle');
  if (bt) {
    bt.setAttribute('aria-pressed', tema === 'claro' ? 'true' : 'false');
    bt.setAttribute('aria-label',
      tema === 'claro' ? 'Cambiar a tema oscuro' : 'Cambiar a tema claro');
  }
  try { localStorage.setItem(TEMA_CLAVE, tema); } catch (e) { /* da igual */ }
}

/* El tema se fija ANTES de que pinte nada, para que no haya un fogonazo
   oscuro al cargar en claro. Por eso este fichero va en el <head>. */
aplicarTema(leerTema());

function montarToggle() {
  const bt = document.querySelector('.tema-toggle');
  if (!bt) return;
  aplicarTema(document.documentElement.dataset.tema || 'oscuro');
  bt.onclick = () => aplicarTema(
    document.documentElement.dataset.tema === 'claro' ? 'oscuro' : 'claro');
}

/* -------------------------------------------------------- dónde estoy
   Resalta el enlace de la sección visible. Es un IntersectionObserver, no
   un router: la página sigue siendo una sola y larga, que es lo que el
   resto del panel da por hecho. Si el observador no existiera, lo único
   que se pierde es el resaltado. */
function montarScrollSpy() {
  const enlaces = [...document.querySelectorAll('nav.barra .barra-enlaces a')];
  if (!enlaces.length || !('IntersectionObserver' in window)) return;

  const porId = new Map();
  enlaces.forEach((a) => {
    const id = a.getAttribute('href').slice(1);
    const seccion = document.getElementById(id);
    if (seccion) porId.set(seccion, a);
  });
  if (!porId.size) return;

  const visibles = new Set();
  const observador = new IntersectionObserver((entradas) => {
    entradas.forEach((e) => {
      if (e.isIntersecting) visibles.add(e.target); else visibles.delete(e.target);
    });
    // De las que se ven, manda la que esté más arriba en el documento.
    let arriba = null;
    visibles.forEach((s) => {
      if (!arriba || s.offsetTop < arriba.offsetTop) arriba = s;
    });
    enlaces.forEach((a) => a.classList.remove('aqui'));
    if (arriba && porId.get(arriba)) porId.get(arriba).classList.add('aqui');
  }, {rootMargin: '-15% 0px -70% 0px', threshold: 0});

  porId.forEach((_, seccion) => observador.observe(seccion));
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    montarToggle(); montarScrollSpy();
  });
} else {
  montarToggle(); montarScrollSpy();
}
