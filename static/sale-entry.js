'use strict';
(() => {
  const prices=JSON.parse(document.getElementById('product-prices').textContent);
  const product=document.querySelector('[name="product_id"]'),quantity=document.querySelector('[name="quantity"]'),gross=document.querySelector('[name="sale_price"]');
  const button=document.getElementById('use-product-price'),hint=document.getElementById('product-price-hint');
  function suggest(){
    const price=Number(prices[product.value]||0),qty=Number(quantity.value||0);
    const valid=price>0&&Number.isInteger(qty)&&qty>0;
    button.disabled=!valid;
    hint.textContent=valid?`Current selling price: $${price.toFixed(2)} each · $${(price*qty).toFixed(2)} for ${qty} units`:'No selling price set. Enter the sale total, or set a price from the product history screen.';
  }
  button.addEventListener('click',()=>{gross.value=(Number(prices[product.value]||0)*Number(quantity.value||0)).toFixed(2);});
  product.addEventListener('change',suggest);quantity.addEventListener('input',suggest);suggest();
})();
