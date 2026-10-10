/* VendIQ · barra lateral — trasplante fiel de la de mi web personal (commit da6f96b)
   ========================================================================
   ADITIVO. Construye una barra lateral `.sb` a partir de la navegación que YA
   existe (nav.barra): mismos grupos, enlaces, iconos y badges — ni una palabra
   nueva, los textos salen del propio HTML. A ≥960 oculta nav.barra (vía
   `html.shell` en barra.css) y enseña la `.sb`, con grupos plegables + memoria
   + scroll-spy con bloqueo al clic. Si algo aquí falla, no se añade `html.shell`
   y el panel sigue con nav.barra tal cual: no se pierde navegación.

   Reutiliza, casi literal, la mecánica probada de mi web: plegar/enganchar
   (plegado con memoria) y calcular/vigilar/marcarActiva/fijar (scroll-spy).
   Adaptado a VendIQ: el menú se lee del DOM en vez de un MAPA fijo (aquí los
   textos viven en el HTML), y las secciones se ordenan por posición en el
   documento (el orden del menú NO coincide con el del documento y el spy va por
   geometría). Sin segundo nivel: VendIQ casi no tiene sub-destinos reales y el
   panel se quiere limpio. */
(function(){
 'use strict';
 const barraVieja = document.querySelector('nav.barra');
 const principal  = document.querySelector('main.envoltorio');
 if(!barraVieja || !principal) return;
 const enlacesViejos = barraVieja.querySelector('.barra-enlaces');
 if(!enlacesViejos) return;

 const crear=(tag,clase,texto)=>{const e=document.createElement(tag);
  if(clase)e.className=clase;if(texto!=null)e.textContent=texto;return e;};
 const NS='http://www.w3.org/2000/svg';
 const chevron=()=>{const s=document.createElementNS(NS,'svg');
  s.setAttribute('viewBox','0 0 24 24');s.setAttribute('class','sb-chev');
  s.setAttribute('aria-hidden','true');s.innerHTML='<path d="M9.5 5.5 16 12l-6.5 6.5"/>';return s;};

 /* ── leer la navegación que ya existe ──
    .barra-enlaces es una secuencia de <p.nav-grupo> seguidos de sus <a href>. */
 const grupos=[];
 let grupo=null;
 [...enlacesViejos.children].forEach(nodo=>{
  if(nodo.classList.contains('nav-grupo')){grupo={nombre:nodo.textContent.trim(),enlaces:[]};grupos.push(grupo);}
  else if(nodo.tagName==='A' && grupo){grupo.enlaces.push(nodo);}
 });
 if(!grupos.length) return;

 /* ── plegado con memoria (de mi web, literal salvo nombres) ──
    max-height a la altura real y, al terminar, se suelta a `none` para que la
    lista pueda crecer. Cerrada queda inerte: ni se tabula ni se pulsa. */
 const CLAVE_MENU='vendiq-menu';
 let recordado={};
 try{recordado=JSON.parse(localStorage.getItem(CLAVE_MENU)||'{}')||{};}catch(e){recordado={};}
 if(typeof recordado!=='object'||!recordado)recordado={};
 const defecto=(clave,val)=>typeof recordado[clave]==='boolean'?recordado[clave]:val;
 const recordar=(clave,abierto)=>{recordado[clave]=abierto;
  try{localStorage.setItem(CLAVE_MENU,JSON.stringify(recordado));}catch(e){}};
 const menosMov=()=>!!(window.matchMedia&&matchMedia('(prefers-reduced-motion:reduce)').matches);
 let nCaja=0;
 function plegar(boton,caja,marca,abierto,animar){
  marca.classList.toggle('abierto',abierto);
  boton.setAttribute('aria-expanded',abierto?'true':'false');
  caja.inert=!abierto;
  if(!animar||menosMov()){caja.style.maxHeight=abierto?'none':'0px';return;}
  if(abierto){
   caja.style.maxHeight=caja.scrollHeight+'px';
   const soltar=()=>{if(marca.classList.contains('abierto'))caja.style.maxHeight='none';};
   const fin=ev=>{if(ev.target!==caja||ev.propertyName!=='max-height')return;
    caja.removeEventListener('transitionend',fin);soltar();};
   caja.addEventListener('transitionend',fin);
   setTimeout(soltar,400);                 // red por si no llega el evento
  }else{
   caja.style.maxHeight=caja.scrollHeight+'px';
   caja.getBoundingClientRect();           // reflujo: sin altura de partida no hay animación
   caja.style.maxHeight='0px';
  }
 }
 function enganchar(boton,caja,marca,clave,pordefecto){
  caja.id='sb-caja-'+(++nCaja);boton.setAttribute('aria-controls',caja.id);
  boton.onclick=()=>{const ab=!marca.classList.contains('abierto');
   plegar(boton,caja,marca,ab,true);recordar(clave,ab);};
  plegar(boton,caja,marca,defecto(clave,pordefecto),false);
 }

 /* ── construir la .sb a partir de lo leído ── */
 const sb=crear('nav','sb');sb.setAttribute('aria-label','Secciones');
 const marcaOrig=barraVieja.querySelector('.marca');
 if(marcaOrig){
  const m=marcaOrig.cloneNode(true);
  // Solo el glifo: el nombre «VendIQ» al lado del logo sobra (el hero ya lo dice).
  m.querySelectorAll('span:not(.glifo)').forEach(s=>s.remove());
  sb.append(m);
 }
 const lista=crear('div','sb-links');
 grupos.forEach(g=>{
  const filas=g.enlaces.filter(a=>document.querySelector(a.getAttribute('href')));
  if(!filas.length)return;
  const sec=crear('div','sb-sec');
  const cab=crear('button','sb-grupo');cab.type='button';
  cab.append(chevron(),crear('span',null,g.nombre));
  const caja=crear('div','sb-lista');
  filas.forEach(a=>{
   const na=crear('a');na.href=a.getAttribute('href');
   const ico=a.querySelector('svg');
   if(ico){const c=ico.cloneNode(true);c.setAttribute('class','sb-ico');na.append(c);}
   const span=a.querySelector('span');
   na.append(crear('span',null,span?span.textContent.trim():na.getAttribute('href').slice(1)));
   const badge=a.querySelector('.nav-badge');
   if(badge){const b=badge.cloneNode(true);b.className='sb-badge';na.append(b);} // conserva data-badge y hidden
   caja.append(na);
  });
  sec.append(cab,caja);
  enganchar(cab,caja,sec,'g:'+g.nombre,true);   // los grupos nacen abiertos
  lista.append(sec);
 });
 sb.append(lista);

 /* ── el pie: el interruptor de tema (clonado; lo cablea tema.js, que ahora
    cablea TODOS los .tema-toggle) y el «en vivo» (movido, conserva su id y lo
    sigue actualizando panel.js). ── */
 const pie=crear('div','sb-pie');
 const toggle=barraVieja.querySelector('.tema-toggle');
 if(toggle)pie.append(toggle.cloneNode(true));
 // El «en vivo» (5000 piezas · índice cargado) NO va en la lateral: sobra ahí.
 // Se queda en nav.barra, que sólo se ve en móvil.
 if(pie.children.length)sb.append(pie);

 document.body.insertBefore(sb,barraVieja);
 document.documentElement.classList.add('shell');

 /* ── scroll-spy (de mi web; `calcular` adaptado al orden en el documento) ──
    Un IntersectionObserver nuevo. Su raíz es la franja de arriba hasta LINEA;
    en cada aviso se recalcula por geometría, así da igual quién lo disparó. */
 const SECCIONES=[];
 lista.querySelectorAll('.sb-sec>.sb-lista>a').forEach(n=>{
  const dest=document.querySelector(n.getAttribute('href'));
  if(dest)SECCIONES.push({href:n.getAttribute('href'),a:n,destino:dest});
 });
 if(!SECCIONES.length)return;
 // El orden del menú no es el del documento: se ordena por posición real, que
 // es lo que el spy (por geometría) da por hecho.
 SECCIONES.sort((x,y)=>(x.destino.compareDocumentPosition(y.destino)&Node.DOCUMENT_POSITION_PRECEDING)?1:-1);

 let activa=null;
 function marcarActiva(href){
  if(href===activa)return;activa=href;
  SECCIONES.forEach(s=>{const es=s.href===href;s.a.classList.toggle('aqui',es);
   if(es)s.a.setAttribute('aria-current','location');else s.a.removeAttribute('aria-current');});
  lista.querySelectorAll('.sb-sec').forEach(sec=>sec.classList.toggle('tiene-activa',!!sec.querySelector('a.aqui')));
  // Que el activo no quede fuera de vista si la lista scrollea. A mano y no con
  // scrollIntoView, que cortaría el desplazamiento suave de la página.
  const s=SECCIONES.find(z=>z.href===href);
  const suGrupo=s&&s.a.closest('.sb-sec');
  if(s&&suGrupo&&suGrupo.classList.contains('abierto')&&lista.scrollHeight>lista.clientHeight){
   const r=s.a.getBoundingClientRect(),caja=lista.getBoundingClientRect();
   if(r.top<caja.top+8){const y=lista.scrollTop-(caja.top+8-r.top);lista.scrollTop=y<40?0:y;}
   else if(r.bottom>caja.bottom-8)lista.scrollTop+=r.bottom-caja.bottom+8;}
 }

 const LINEA=112;             // = ancla aprox. + aire: tras un salto, el destino queda por encima
 let bloqueo=0;               // tras un clic, el spy no manda hasta que acaba el desplazamiento
 function calcular(){
  if(Date.now()<bloqueo)return;
  const raiz=document.documentElement;
  if(window.innerHeight+window.scrollY>=raiz.scrollHeight-2){
   marcarActiva(SECCIONES[SECCIONES.length-1].href);return;}   // al final, la última
  let cual=null,mejor=-Infinity;   // en el hero ninguna pasó la línea: no se marca nada
  SECCIONES.forEach(s=>{const t=s.destino.getBoundingClientRect().top;
   if(t<=LINEA&&t>mejor){mejor=t;cual=s.href;}});               // la más baja que aún no pasó la línea
  marcarActiva(cual);
 }
 let spy=null;
 function vigilar(){
  if(!('IntersectionObserver'in window)){calcular();return;}
  if(spy)spy.disconnect();
  spy=new IntersectionObserver(calcular,
   {rootMargin:'0px 0px '+(-Math.max(0,window.innerHeight-LINEA))+'px 0px',threshold:[0,1]});
  SECCIONES.forEach(s=>{if(s.destino!==principal)spy.observe(s.destino);});
 }
 vigilar();calcular();
 let tRs=null;
 window.addEventListener('resize',()=>{clearTimeout(tRs);tRs=setTimeout(()=>{vigilar();calcular();},180);});
 // Red: un salto muy largo puede cruzar la franja entre dos fotogramas.
 window.addEventListener('scrollend',()=>{bloqueo=0;calcular();});

 const fijar=href=>{marcarActiva(href);bloqueo=Date.now()+1200;};
 lista.addEventListener('click',e=>{const a=e.target.closest('a');if(!a)return;
  fijar(a.getAttribute('href'));});
})();
