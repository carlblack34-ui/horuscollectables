'use strict';
(() => {
  const data = JSON.parse(document.getElementById('catalogue-data').textContent);
  const game = document.getElementById('tcg'), era = document.getElementById('era'), set = document.getElementById('set_name');
  const type = document.getElementById('product_type'), product = document.getElementById('category'), condition = document.getElementById('condition');
  const name = document.getElementById('item-name'); let manualName = !!name.value;
  const conditions = {sealed:['Sealed','Opened / incomplete','Damaged packaging'],singles:['Raw NM','Raw LP','Raw MP','Raw HP','Raw DMG'],graded:['PSA 10','PSA 9','PSA 8','CGC 10','CGC Pristine 10','CGC 9.5','CGC 9','BGS 10','BGS 9.5','BGS 9','Other Graded'],accessories:['New','Used','Damaged']};
  function fill(select, values, selected, placeholder, preserve=false) {
    select.replaceChildren(new Option(placeholder,''));
    values.forEach(v => select.add(new Option(select === set && v === 'Sun & Moon' ? 'Sun & Moon Base' : v,v)));
    if (preserve && selected && !values.includes(selected)) select.add(new Option(selected,selected));
    select.value = selected || ''; select.disabled = !values.length && !selected;
  }
  function renderPath() {
    const parts = [game,era,set,product].filter(s=>s.value).map(s=>s.selectedOptions[0].textContent);
    document.getElementById('selection-path').textContent=parts.join(' → ');
    if (!manualName) name.value=[set.value,product.value].filter(Boolean).join(' · ');
    document.querySelectorAll('[data-game]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.game===game.value)));
    document.querySelectorAll('[data-type]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.type===type.value)));
  }
  function updateSets(initial=false) { fill(set,(data.catalogue[game.value]||{})[era.value]||[],initial?set.dataset.initial:'','Choose a set',initial); renderPath(); }
  function updateEras(initial=false) {
    fill(era,Object.keys(data.catalogue[game.value]||{}),initial?era.dataset.initial:'','Choose an era / series',initial);
    updateSets(initial);
    document.getElementById('catalogue-help').textContent=game.value && !Object.keys(data.catalogue[game.value]||{}).length ? 'This game is ready for your catalogue. Click Manage catalogue to add an era and set, then return here.' : 'Missing an option? Add it once in Manage catalogue. Pokémon starter lists use English expansions; add regional sets separately.';
  }
  function updateProducts(initial=false) {
    const options=type.value==='sealed' ? (data.gameProducts[game.value] || ['Booster Box','Booster Pack','Starter Deck','Collection Box','Display Case','Other Sealed Product']) : data.products[type.value];
    fill(product,options||[],initial?product.dataset.initial:'','Choose a product',initial);
    fill(condition,conditions[type.value]||[],initial?condition.dataset.initial:'', 'Choose a condition',initial);
    if (!initial && type.value==='sealed') condition.value='Sealed';
    renderPath();
  }
  name.addEventListener('input',()=>{manualName=!!name.value;});
  game.addEventListener('change',()=>{updateEras();updateProducts();}); era.addEventListener('change',()=>updateSets());
  set.addEventListener('change',renderPath); product.addEventListener('change',renderPath);
  type.addEventListener('change',()=>updateProducts());
  document.querySelectorAll('[data-game]').forEach(b=>b.addEventListener('click',()=>{game.value=b.dataset.game; updateEras(); updateProducts(); era.focus();}));
  document.querySelectorAll('[data-type]').forEach(b=>b.addEventListener('click',()=>{type.value=b.dataset.type; updateProducts(); product.focus();}));
  updateEras(true); updateProducts(true);
})();
