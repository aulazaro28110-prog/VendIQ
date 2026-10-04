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
  // TODOS los interruptores: el de nav.barra y el que barra.js clona en la
  // lateral. querySelectorAll para que los dos muestren el mismo estado.
  document.querySelectorAll('.tema-toggle').forEach((bt) => {
    bt.setAttribute('aria-pressed', tema === 'claro' ? 'true' : 'false');
    bt.setAttribute('aria-label',
      tema === 'claro' ? 'Cambiar a tema oscuro' : 'Cambiar a tema claro');
  });
  try { localStorage.setItem(TEMA_CLAVE, tema); } catch (e) { /* da igual */ }
}

/* El tema se fija ANTES de que pinte nada, para que no haya un fogonazo
   oscuro al cargar en claro. Por eso este fichero va en el <head>.

   Y de paso, `montando`: a ≥960 barra.css la usa para ocultar la nav vieja y
   reservar el hueco de la lateral desde el primer fotograma, de modo que no se
   vea la barra antigua ni dé un salto el contenido mientras barra.js monta la
   `.sb`. Se quita al cargar; si el montaje fallara, vuelve la barra de siempre. */
aplicarTema(leerTema());
document.documentElement.classList.add('montando');

function montarToggle() {
  const toggles = document.querySelectorAll('.tema-toggle');
  if (!toggles.length) return;
  aplicarTema(document.documentElement.dataset.tema || 'oscuro');
  toggles.forEach((bt) => {
    bt.onclick = () => aplicarTema(
      document.documentElement.dataset.tema === 'claro' ? 'oscuro' : 'claro');
  });
}

/* -------------------------------------------------------- dónde estoy
   Resalta el enlace de la sección visible. Es un IntersectionObserver, no
   un router: la página sigue siendo una sola y larga, que es lo que el
   resto del panel da por hecho. Si el observador no existiera, lo único
   que se pierde es el resaltado. */
function montarScrollSpy() {
  const enlaces = [...document.querySelectorAll('nav.barra .barra-enlaces a')];
  if (!enlaces.length || !('IntersectionObserver' in window)) return;

  const seccionDe = (a) => document.getElementById(a.getAttribute('href').slice(1));
  const porId = new Map();
  enlaces.forEach((a) => {
    const seccion = seccionDe(a);
    if (seccion) porId.set(seccion, a);
  });
  if (!porId.size) return;

  const marcar = (a) => enlaces.forEach((x) => x.classList.toggle('aqui', x === a));

  // De las que se ven, manda la que esté más arriba en el documento.
  const visibles = new Set();
  const reconciliar = () => {
    let arriba = null;
    visibles.forEach((s) => { if (!arriba || s.offsetTop < arriba.offsetTop) arriba = s; });
    if (arriba) marcar(porId.get(arriba));
  };

  // Al pulsar un enlace, la sección se marca YA y el observador se congela
  // mientras la página se desliza, para que el resaltado no vaya parpadeando
  // por las secciones intermedias. Se suelta cuando el scroll termina
  // (scrollend) o, si el navegador no lo soporta, tras una espera corta.
  let bloqueado = false;
  let temporizador;
  const soltar = () => { bloqueado = false; reconciliar(); };
  enlaces.forEach((a) => {
    if (!porId.has(seccionDe(a))) return;
    a.addEventListener('click', () => {
      marcar(a);
      bloqueado = true;
      clearTimeout(temporizador);
      temporizador = setTimeout(soltar, 700);
    });
  });
  if ('onscrollend' in window) {
    window.addEventListener('scrollend', () => {
      if (!bloqueado) return;
      clearTimeout(temporizador);
      soltar();
    });
  }

  const observador = new IntersectionObserver((entradas) => {
    entradas.forEach((e) => {
      if (e.isIntersecting) visibles.add(e.target); else visibles.delete(e.target);
    });
    if (!bloqueado) reconciliar();
  }, {rootMargin: '-15% 0px -70% 0px', threshold: 0});

  porId.forEach((_, seccion) => observador.observe(seccion));
}

function arrancar() {
  montarToggle(); montarScrollSpy();
  // La lateral ya está montada (barra.js corre al final del body, antes de
  // esto): se destapa. Si barra.js hubiera fallado, no habrá `shell` y al
  // quitar `montando` reaparece la nav de siempre.
  document.documentElement.classList.remove('montando');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', arrancar);
} else {
  arrancar();
}
