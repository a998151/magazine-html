(function(){
  var root=document.documentElement, K='mepub';
  function $(id){ return document.getElementById(id); }
  function get(k,d){try{return localStorage.getItem(K+k)||d}catch(e){return d}}
  function set(k,v){try{localStorage.setItem(K+k,v)}catch(e){}}

  var drawer=$('drawer'), scrim=$('scrim');
  var secs=[].slice.call(document.querySelectorAll('section.doc'));
  var links=[].slice.call(document.querySelectorAll('#drawer a'));

  // 状态以内存为准：file:// 下浏览器可能禁用 localStorage，
  // 若以存储为源，设置会写不进去、读出来还是旧值，按钮就等于没反应。
  var state = {
    fs: parseFloat(get('fs','18px')) || 18,
    lh: get('lh','1.85') || '1.85',
    theme: get('theme','paper') || 'paper'
  };

  function apply(){
    root.setAttribute('data-theme',state.theme);
    root.style.setProperty('--fs',state.fs+'px');
    root.style.setProperty('--lh',state.lh);
    var v=$('fsv'); if(v) v.textContent=Math.round(state.fs);
    var l=$('lhv'); if(l) l.textContent=state.lh;
    [].slice.call(document.querySelectorAll('.swatches button')).forEach(function(b){
      b.classList.toggle('on', b.getAttribute('data-act')==='theme:'+state.theme);
    });
  }

  function toggle(on){
    if(on===undefined) on=!drawer.classList.contains('on');
    drawer.classList.toggle('on',on); scrim.classList.toggle('on',on);
  }

  // 事件委托：任何带 data-act 的按钮都走这一条路径，不会漏绑
  document.addEventListener('click',function(e){
    var b=e.target.closest ? e.target.closest('[data-act]') : null;
    if(!b) return;
    var act=b.getAttribute('data-act');
    if(act==='fs+'||act==='fs-'){
      state.fs=Math.max(14,Math.min(28,state.fs+(act==='fs+'?1:-1)));
      set('fs',state.fs+'px'); apply();
    } else if(act==='lh+'||act==='lh-'){
      state.lh=Math.max(1.4,Math.min(2.4,parseFloat(state.lh)+(act==='lh+'?0.1:-0.1))).toFixed(2);
      set('lh',state.lh); apply();
    } else if(act.indexOf('theme:')===0){
      state.theme=act.slice(6); set('theme',state.theme); apply();
    } else if(act==='menu'||act==='cur'){
      toggle();
    } else if(act==='close'){
      toggle(false);
    } else if(act==='top'){
      window.scrollTo({top:0,behavior:'smooth'});
    }
  });

  scrim.addEventListener('click',function(){ toggle(false) });
  links.forEach(function(a){ a.addEventListener('click',function(){ toggle(false) }); });

  function cur(){ var y=window.scrollY+140, i=0;
    secs.forEach(function(s,k){ if(s.offsetTop<=y) i=k }); return i; }
  function go(i){ if(i<0)i=0; if(i>=secs.length)i=secs.length-1;
    window.scrollTo({top:Math.max(0,secs[i].offsetTop-64),behavior:'smooth'}); }

  window.addEventListener('keydown',function(e){
    if(e.target && /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
    var i=cur();
    if(e.key==='ArrowRight'||e.key==='j'){go(i+1);e.preventDefault()}
    else if(e.key==='ArrowLeft'||e.key==='k'){go(i-1);e.preventDefault()}
    else if(e.key==='Home'){go(0);e.preventDefault()}
    else if(e.key==='End'){go(secs.length-1);e.preventDefault()}
    else if(e.key==='Escape'){toggle(false)}
    else if(e.key==='m'||e.key==='M'){toggle()}
  });

  var bar=$('prog'), now=$('now'), top=$('topbtn');
  function tick(){
    var h=document.body.scrollHeight-window.innerHeight;
    bar.style.width=(h>0?Math.min(100,window.scrollY/h*100):0)+'%';
    var i=cur();
    links.forEach(function(a,k){ a.classList.toggle('on',k===i) });
    if(secs[i]){ now.textContent=secs[i].getAttribute('data-title')||'' }
    if(top) top.classList.toggle('on', window.scrollY>600);
  }
  window.addEventListener('scroll',tick,{passive:true});
  window.addEventListener('resize',tick);

  var lamp=$('lamp'), limg=$('limg'), lcap=$('lcap');
  document.addEventListener('click',function(e){
    var img=e.target;
    if(img && img.tagName==='IMG' && img.closest('figure')){
      var fc=img.closest('figure').querySelector('figcaption');
      limg.src=img.src; lcap.textContent=fc?fc.innerText:'';
      lamp.classList.add('on'); e.preventDefault();
    }
  });
  lamp.addEventListener('click',function(){ lamp.classList.remove('on') });

  apply(); tick();
})();
