// Alternância de tema claro/escuro. Sem escolha salva, segue o sistema.
(function(){
  var root=document.documentElement, KEY='tema';
  function get(){try{return localStorage.getItem(KEY)}catch(e){return null}}
  function set(v){try{v?localStorage.setItem(KEY,v):localStorage.removeItem(KEY)}catch(e){}}
  var saved=get(); if(saved==='light'||saved==='dark') root.setAttribute('data-theme',saved);
  function current(){var t=root.getAttribute('data-theme'); if(t) return t; return window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}
  function label(b){b.textContent=current()==='dark'?'Tema claro':'Tema escuro'}
  document.addEventListener('DOMContentLoaded',function(){
    var b=document.getElementById('tema'); if(!b) return; label(b);
    b.addEventListener('click',function(){var n=current()==='dark'?'light':'dark';root.setAttribute('data-theme',n);set(n);label(b)});
  });
})();
