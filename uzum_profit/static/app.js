// Umumiy: formalarni "orqaga" tugmasi buzmasdan yuborish (POST -> redirect), band tugma, xabarni URL'dan olib tashlash.
(function () {
  'use strict';

  // ?msg=... faqat bir marta ko'rsatiladi: yangilaganda yoki orqaga qaytganda qayta chiqmasin
  try {
    if (location.search.indexOf('msg=') !== -1 && window.history && history.replaceState) {
      history.replaceState(null, '', location.pathname + location.search
        .replace(/([?&])msg=[^&]*&?/, '$1').replace(/[?&]$/, ''));
    }
  } catch (err) { /* muhim emas */ }

  if (!window.fetch) { return; }

  function encode(form) {
    var parts = [], els = form.elements, i, el, j;
    for (i = 0; i < els.length; i++) {
      el = els[i];
      if (!el.name || el.disabled || el.type === 'submit' || el.type === 'button') { continue; }
      if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) { continue; }
      if (el.tagName === 'SELECT' && el.multiple) {
        for (j = 0; j < el.options.length; j++) {
          if (el.options[j].selected) { parts.push(encodeURIComponent(el.name) + '=' + encodeURIComponent(el.options[j].value)); }
        }
      } else {
        parts.push(encodeURIComponent(el.name) + '=' + encodeURIComponent(el.value));
      }
    }
    return parts.join('&');
  }

  document.addEventListener('submit', function (e) {
    var form = e.target, btn, label, isSync;
    if (e.defaultPrevented || !form || !form.method || form.method.toLowerCase() !== 'post') { return; }
    e.preventDefault();
    if (form.getAttribute('data-busy')) { return; }
    form.setAttribute('data-busy', '1');
    btn = form.querySelector('button:not([type=button])');
    label = btn ? btn.textContent : '';
    isSync = form.getAttribute('action') === '/sync';
    if (btn) { btn.disabled = true; if (isSync) { btn.textContent = 'Yangilanmoqda... (bir necha daqiqa olishi mumkin)'; } }

    function restore() {
      form.removeAttribute('data-busy');
      if (btn) { btn.disabled = false; btn.textContent = label; }
    }

    fetch(form.getAttribute('action') || location.pathname, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      // sinxronizatsiyadan keyin shu sahifaning o'ziga qaytiladi
      body: encode(form) + (isSync ? '&next=' + encodeURIComponent(location.pathname + location.search) : '')
    }).then(function (r) {
      if (r.redirected) { location.replace(r.url); return null; }   // joriy sahifa tarixdan almashadi
      return r.text().then(function (html) {                         // xatolar bilan qayta chizilgan forma
        document.open(); document.write(html); document.close();
      });
    }).catch(function () {
      restore();
      alert("Server bilan aloqa yo'q. Dastur (serve) ishlab turganini tekshiring.");
    });
  });

  // Enter bosilganda forma tasodifan yuborilmasin (qatorlarda Enter o'z vazifasini bajaradi)
  document.addEventListener('keydown', function (e) {
    var t = e.target;
    if (e.key === 'Enter' && t && t.tagName === 'INPUT' && t.form && t.form.id === 'bform' &&
        t.type !== 'submit' && t.type !== 'button' && !e.defaultPrevented) {
      e.preventDefault();
    }
  });
}());
