'use strict';
(() => {
  const data=JSON.parse(document.getElementById('catalogue-data').textContent);
  const $=id=>document.getElementById(id);
  const form=$('stock-builder'), game=$('tcg'), era=$('era'), set=$('set_name'), type=$('product_type'), product=$('category'), condition=$('condition'), name=$('item-name');
  let manualName=!!name.value, step=0;
  const panels=[...document.querySelectorAll('[data-panel]')], stepTabs=[...document.querySelectorAll('[data-step]')];
  const conditions={sealed:['Sealed','Opened / incomplete','Damaged packaging'],singles:['Raw NM','Raw LP','Raw MP','Raw HP','Raw DMG'],graded:['PSA 10','PSA 9','PSA 8','CGC 10','CGC Pristine 10','CGC 9.5','CGC 9','BGS 10','BGS 9.5','BGS 9','Other Graded'],accessories:['New','Used','Damaged']};
  function fill(select,values,selected,placeholder,preserve=false){
    select.replaceChildren(new Option(placeholder,''));
    values.forEach(v=>select.add(new Option(select===set&&v==='Sun & Moon'?'Sun & Moon Base':v,v)));
    if(preserve&&selected&&!values.includes(selected))select.add(new Option(selected,selected));
    select.value=selected||'';select.disabled=!values.length&&!selected;
  }
  function tiles(id,select,onPick,query=''){
    const container=$(id);container.replaceChildren();
    const options=[...select.options].filter(o=>o.value&&o.textContent.toLowerCase().includes(query.toLowerCase()));
    options.forEach(o=>{
      const button=document.createElement('button');button.type='button';button.className='picker-tile';button.textContent=o.textContent;button.setAttribute('aria-pressed',String(select.value===o.value));
      button.addEventListener('click',()=>{select.value=o.value;onPick();});container.appendChild(button);
    });
    if(!options.length){const empty=document.createElement('p');empty.className='picker-empty';empty.textContent=query?'No sets match that search.':'Choose the previous option, or add missing choices in the TCG library.';container.appendChild(empty);}
  }
  function path(){
    $('selection-path').textContent=[game,era,set,product].filter(s=>s.value).map(s=>s.selectedOptions[0].textContent).join(' → ')||'Choose a game to get started.';
    if(!manualName)name.value=[set.value,product.value].filter(Boolean).join(' · ');
    document.querySelectorAll('[data-game]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.game===game.value)));
    document.querySelectorAll('[data-type]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.type===type.value)));
  }
  function setTiles(){tiles('set-tiles',set,()=>{path();setTiles();},$('set-search').value);}
  function sets(initial=false){
    fill(set,(data.catalogue[game.value]||{})[era.value]||[],initial?set.dataset.initial:'','Choose a set',initial);
    $('set-search').value='';setTiles();path();
    tiles('era-tiles',era,()=>sets());
  }
  function eras(initial=false){
    fill(era,Object.keys(data.catalogue[game.value]||{}),initial?era.dataset.initial:'','Choose an era',initial);sets(initial);
    $('catalogue-help').textContent=game.value&&!Object.keys(data.catalogue[game.value]||{}).length?'Add this game’s eras and sets in the TCG library, then come back here.':'Tap an era, then find your expansion below.';
  }
  function products(initial=false){
    const options=type.value==='sealed'?(data.gameProducts[game.value]||['Booster Box','Booster Pack','Starter Deck','Collection Box','Display Case','Other Sealed Product']):data.products[type.value];
    fill(product,options||[],initial?product.dataset.initial:'','Choose a product',initial);
    fill(condition,conditions[type.value]||[],initial?condition.dataset.initial:'','Choose a condition',initial);
    if(!initial&&type.value==='sealed')condition.value='Sealed';
    tiles('product-tiles',product,productsPicked);path();
  }
  function productsPicked(){path();tiles('product-tiles',product,productsPicked);}
  function fail(message){$('wizard-error').hidden=false;$('wizard-error').textContent=message;}
  function valid(index){
    if(index===0&&!game.value){fail('Pick a game to continue.');return false;}
    if(index===1&&(!era.value||!set.value)){fail('Choose an era and a set. Missing options can be added in the TCG library.');return false;}
    if(index===2&&(!product.value||!name.value.trim())){fail('Choose a product and give your stock a name.');return false;}
    return true;
  }
  function show(index){
    step=index;panels.forEach((p,i)=>p.hidden=i!==index);stepTabs.forEach((b,i)=>{b.classList.toggle('active',i===index);b.setAttribute('aria-current',i===index?'step':'false');});
    $('wizard-back').disabled=index===0;$('wizard-next').hidden=index===3;$('step-counter').textContent=`Step ${index+1} of 4`;$('wizard-error').hidden=true;
  }
  form.classList.add('builder-enhanced');$('wizard-controls').hidden=false;
  name.addEventListener('input',()=>{manualName=!!name.value;});
  $('set-search').addEventListener('input',setTiles);
  game.addEventListener('change',()=>{eras();products();});era.addEventListener('change',()=>sets());set.addEventListener('change',()=>{path();setTiles();});
  type.addEventListener('change',()=>products());product.addEventListener('change',productsPicked);
  document.querySelectorAll('[data-game]').forEach(b=>b.addEventListener('click',()=>{game.value=b.dataset.game;eras();products();show(1);}));
  document.querySelectorAll('[data-type]').forEach(b=>b.addEventListener('click',()=>{type.value=b.dataset.type;products();}));
  $('wizard-back').addEventListener('click',()=>show(Math.max(0,step-1)));
  $('wizard-next').addEventListener('click',()=>{if(valid(step))show(Math.min(3,step+1));});
  stepTabs.forEach(b=>b.addEventListener('click',()=>{const target=Number(b.dataset.step);if(target>step){for(let i=0;i<target;i++)if(!valid(i)){show(i);valid(i);return;}}show(target);}));
  form.addEventListener('submit',event=>{
    for(let i=0;i<3;i++)if(!valid(i)){event.preventDefault();show(i);valid(i);return;}
    const invalid=[...form.querySelectorAll('input,select,textarea')].find(field=>!field.disabled&&!field.checkValidity());
    if(invalid){event.preventDefault();const panel=invalid.closest('[data-panel]');show(Number(panel.dataset.panel));const extra=invalid.closest('details');if(extra)extra.open=true;invalid.reportValidity();}
  });
  eras(true);products(true);show(0);
})();
