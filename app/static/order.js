// Mobile order entry with offline queue. Orders are saved in localStorage when the network is down and
// re-sent later; the client_uuid makes the server ignore duplicates, so a retry can never create two orders.
(function () {
  const $ = s => document.querySelector(s);
  let catalog = null, rows = [];
  const money = p => (p / 100).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const queue = () => JSON.parse(localStorage.getItem('oto_queue') || '[]');
  const setQueue = q => { localStorage.setItem('oto_queue', JSON.stringify(q)); renderQueue(); };
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : Date.now() + '-' + Math.random().toString(16).slice(2));

  async function loadCatalog() {
    try { const r = await fetch('/api/catalog'); if (!r.ok) throw 0; catalog = await r.json(); localStorage.setItem('oto_catalog', JSON.stringify(catalog)); }
    catch (e) { const c = localStorage.getItem('oto_catalog'); if (c) { catalog = JSON.parse(c); $('#net').textContent = 'Offline - using saved price list'; } }
    if (!catalog) { $('#form').innerHTML = '<p>Open this page once while online to load the price list.</p>'; return; }
    const sel = $('#customer');
    sel.innerHTML = '<option value="">Select customer…</option>' + catalog.customers.sort((a, b) => b.mine - a.mine)
      .map(c => `<option value="${c.id}">${c.name} (${c.type}, ${c.state})</option>`).join('');
    addRow();
  }
  function priceFor(pid) { const cid = $('#customer').value; return ((catalog.prices[cid] || {})[pid]) ?? catalog.products.find(p => p.id == pid).price_paise; }
  function addRow() {
    const div = document.createElement('div'); div.className = 'orderline';
    div.innerHTML = `<label class="p">Product<select class="prod">${catalog.products.map(p => `<option value="${p.id}">${p.name}</option>`).join('')}</select></label>
      <label>Qty<input class="qty" type="number" min="0" step="any" inputmode="decimal"></label>
      <label>Unit<select class="unit"></select></label><button type="button" class="secondary rm">✕</button>`;
    $('#lines').appendChild(div);
    const prod = div.querySelector('.prod'), unit = div.querySelector('.unit');
    const fill = () => { const p = catalog.products.find(x => x.id == prod.value); unit.innerHTML = p.units.filter(u => u == 'packet' || u == 'carton').map(u => `<option>${u}</option>`).join(''); total(); };
    prod.onchange = fill; fill();
    div.querySelector('.qty').oninput = total; unit.onchange = total; div.querySelector('.rm').onclick = () => { div.remove(); total(); };
  }
  function collect() {
    return [...document.querySelectorAll('.orderline')].map(d => ({item_id: +d.querySelector('.prod').value, qty: d.querySelector('.qty').value, unit: d.querySelector('.unit').value}))
      .filter(l => l.qty && +l.qty > 0);
  }
  function total() {
    let t = 0;
    collect().forEach(l => { const p = catalog.products.find(x => x.id == l.item_id); t += priceFor(l.item_id) * l.qty * (l.unit == 'carton' ? p.carton_size : 1); });
    $('#total').textContent = 'Approx. value (before GST): Rs ' + money(t);
  }
  async function send(order) {
    const r = await fetch('/api/orders', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(order)});
    const j = await r.json().catch(() => ({ok: false, error: 'Bad response'}));
    if (r.status === 401 || r.status === 302) throw new Error('login');
    return j;
  }
  async function flush() {
    let q = queue(); if (!q.length) return;
    const rest = [];
    for (const o of q) { try { const j = await send(o); if (!j.ok) { o.error = j.error; rest.push(o); } } catch (e) { rest.push(o); } }
    setQueue(rest);
  }
  function renderQueue() { const q = queue(); $('#queue').innerHTML = q.length ? `<div class="flash error">${q.length} order(s) waiting to sync${q.some(o => o.error) ? ' - some were rejected: ' + q.filter(o => o.error).map(o => o.error).join('; ') : ''}</div>` : ''; }
  async function submit() {
    const order = {client_uuid: uuid(), customer_id: +$('#customer').value, notes: $('#notes').value, lines: collect()};
    if (!order.customer_id || !order.lines.length) { $('#msg').innerHTML = '<div class="flash error">Select a customer and add a quantity</div>'; return; }
    $('#submit').disabled = true;
    try {
      const j = await send(order);
      if (j.ok) $('#msg').innerHTML = `<div class="flash ok">Order ${j.order_no} sent to the factory</div>`;
      else { $('#msg').innerHTML = `<div class="flash error">${j.error}</div>`; $('#submit').disabled = false; return; }
    } catch (e) {
      setQueue(queue().concat([order]));
      $('#msg').innerHTML = '<div class="flash ok">No network - order saved on this phone and will be sent automatically</div>';
    }
    $('#lines').innerHTML = ''; $('#notes').value = ''; addRow(); total(); $('#submit').disabled = false;
  }
  window.addEventListener('DOMContentLoaded', async () => {
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
    $('#add').onclick = addRow; $('#submit').onclick = submit; $('#customer').onchange = total;
    await loadCatalog(); renderQueue(); flush();
  });
  window.addEventListener('online', flush);
})();
