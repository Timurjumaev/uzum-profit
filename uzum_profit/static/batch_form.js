/* Partiya formasi: SKU qidiruvi (combobox), mahsulot va chiqim qatorlari, kurs tugmalari.
   Tashqi kutubxonasiz. Brauzerda ham, Node'da (sinov uchun) ham yuklanadi. */
(function (root) {
  'use strict';

  // ---------- qidiruv: kirill/lotin harflarga e'tiborsiz, bo'lak bo'yicha ----------
  var TR = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i',
    'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
    'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya', 'ў': 'u', 'қ': 'k', 'ғ': 'g', 'ҳ': 'h'
  };

  function skeleton(s) {
    s = String(s || '').toLowerCase();
    var out = '', i, ch;
    for (i = 0; i < s.length; i++) {
      ch = s.charAt(i);
      out += Object.prototype.hasOwnProperty.call(TR, ch) ? TR[ch] : ch;
    }
    return out.replace(/[`'’ʻʼ‘´]/g, '')
      .replace(/sch/g, 's').replace(/sh/g, 's').replace(/zh/g, 'j').replace(/kh/g, 'h')
      .replace(/ch/g, 'c').replace(/ts/g, 'c').replace(/y([aeiou])/g, '$1')
      .replace(/x/g, 'h').replace(/w/g, 'v').replace(/q/g, 'k').replace(/y/g, 'i');
  }

  function prepare(list) {
    return (list || []).map(function (o) {
      var t = o[0] + ' ' + (o[1] || '');
      return { sku: o[0], title: o[1] || '', stock: o[2], raw: t.toLowerCase(), sk: skeleton(t) };
    });
  }

  function search(items, q, limit) {
    q = String(q || '').trim().toLowerCase();
    if (!q) return items.slice(0, limit);
    var toks = q.split(/\s+/), stoks = toks.map(skeleton), out = [], i, j, it, p, score, ok;
    for (i = 0; i < items.length; i++) {
      it = items[i]; score = 0; ok = true;
      for (j = 0; j < toks.length; j++) {
        p = it.raw.indexOf(toks[j]);
        if (p < 0) { p = it.sk.indexOf(stoks[j]); if (p >= 0) { p += 500; } }
        if (p < 0) { ok = false; break; }
        score += p;
      }
      if (ok) { out.push({ it: it, score: score }); }
    }
    out.sort(function (a, b) {
      return (a.score - b.score) || (a.it.sku < b.it.sku ? -1 : (a.it.sku > b.it.sku ? 1 : 0));
    });
    return out.slice(0, limit).map(function (x) { return x.it; });
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var api = { skeleton: skeleton, prepare: prepare, search: search };
  if (typeof module !== 'undefined' && module.exports) { module.exports = api; }
  root.BatchForm = api;
  if (typeof document === 'undefined' || !document.getElementById('bform')) { return; }

  // ---------- forma ----------
  var LINE_HTML = '<div class="row line">' +
    '<div class="cb"><input type="text" name="line_text" class="cb-input" autocomplete="off" ' +
    'placeholder="SKU qidiring (masalan: spo) yoki yangi nom yozing">' +
    '<input type="hidden" name="line_sku"><div class="dd"></div><div class="hint"></div></div>' +
    '<input type="text" name="line_qty" inputmode="numeric" placeholder="Soni">' +
    '<input type="text" name="line_cny" class="cny" inputmode="decimal" placeholder="CNY narx">' +
    '<button type="button" class="x" title="Qatorni o\'chirish">×</button></div>';
  var EXTRA_HTML = '<div class="row extra">' +
    '<input type="text" name="extra_amount" inputmode="decimal" placeholder="Summa (so\'m)">' +
    '<input type="text" name="extra_name" placeholder="Nima uchun? (masalan: shtrix kod rulon)">' +
    '<button type="button" class="x" title="Qatorni o\'chirish">×</button></div>';

  var form = document.getElementById('bform');
  var catalog = JSON.parse(document.getElementById('catalog').textContent || '{}');
  var initial = JSON.parse(document.getElementById('initial').textContent || '{}');
  var shopSel = document.getElementById('shop');
  var linesBox = document.getElementById('lines');
  var extrasBox = document.getElementById('extras-rows');
  var perPrice = document.getElementById('per-price');
  var cache = {};
  var active = null;   // ochiq ro'yxat: { row, res, idx }

  function items() {
    var id = shopSel.value;
    if (!cache[id]) { cache[id] = prepare(catalog[id] || []); }
    return cache[id];
  }

  function findExact(text) {
    var t = String(text || '').trim().toLowerCase(), list = items(), i;
    if (!t) { return null; }
    for (i = 0; i < list.length; i++) { if (list[i].sku.toLowerCase() === t) { return list[i]; } }
    return null;
  }

  function el(html) {
    var d = document.createElement('div');
    d.innerHTML = html;
    return d.firstChild;
  }

  function parts(row) {
    return { inp: row.querySelector('.cb-input'), hid: row.querySelector('input[name=line_sku]'),
             dd: row.querySelector('.dd'), hint: row.querySelector('.hint') };
  }

  function refresh(row) {
    var p = parts(row), linked = !!p.hid.value, free = !linked && p.inp.value.trim() !== '';
    row.className = 'row line' + (linked ? ' linked' : '') + (free ? ' free' : '');
    p.hint.textContent = free ? "SKU biriktirilmagan: yangi nom sifatida saqlanadi (SKU chiqqach biriktirasiz)" : '';
  }

  function closeDd(row) {
    parts(row).dd.className = 'dd';
    if (active && active.row === row) { active = null; }
  }

  function optionNodes(row) {
    return parts(row).dd.querySelectorAll('.opt[data-i], .opt[data-new]');
  }

  function paint() {
    if (!active) { return; }
    var dd = parts(active.row).dd, opts = optionNodes(active.row), i, o;
    for (i = 0; i < opts.length; i++) { opts[i].classList.toggle('hl', i === active.idx); }
    o = opts[active.idx];
    if (o) {
      if (o.offsetTop < dd.scrollTop) { dd.scrollTop = o.offsetTop; }
      else if (o.offsetTop + o.offsetHeight > dd.scrollTop + dd.clientHeight) {
        dd.scrollTop = o.offsetTop + o.offsetHeight - dd.clientHeight;
      }
    }
  }

  // fromFocus: SKU biriktirilmagan qatorga kirganda butun ro'yxat ko'rsatiladi (nom qidiruv uchun yaroqsiz)
  function openDd(row, fromFocus) {
    var p = parts(row), q = fromFocus ? '' : p.inp.value, res = search(items(), q, 40), html = '', i, t = p.inp.value.trim();
    for (i = 0; i < res.length; i++) {
      html += '<div class="opt" data-i="' + i + '"><b>' + esc(res[i].sku) + '</b>' +
        (res[i].title || res[i].stock != null
          ? '<small>' + esc(res[i].title) + (res[i].stock != null ? ' · omborda: ' + esc(res[i].stock) : '') + '</small>'
          : '') + '</div>';
    }
    if (t && !fromFocus && !findExact(t)) {
      html += '<div class="opt new" data-new="1">+ «' + esc(t) + '» yangi nom sifatida (SKU keyin biriktiriladi)</div>';
    }
    if (!html) {
      html = '<div class="opt empty">Bu do\'konda SKU topilmadi. «API\'dan yangilash»ni bosing yoki yangi nom yozing.</div>';
    }
    p.dd.innerHTML = html;
    p.dd.className = 'dd open';
    active = { row: row, res: res, idx: -1 };
    if (!fromFocus && (res.length || (t && !findExact(t)))) { active.idx = 0; }
    paint();
  }

  function choose(row, which) {
    var p = parts(row), o;
    if (which === 'new') { p.hid.value = ''; }
    else { o = active.res[which]; p.inp.value = o.sku; p.hid.value = o.sku; }
    closeDd(row);
    refresh(row);
    row.querySelector('input[name=line_qty]').focus();
  }

  function addLine(v) {
    v = v || {};
    var row = el(LINE_HTML), p;
    linesBox.appendChild(row);
    p = parts(row);
    p.inp.value = v.text || '';
    p.hid.value = v.sku || '';
    row.querySelector('input[name=line_qty]').value = v.qty || '';
    row.querySelector('input[name=line_cny]').value = v.cny || '';
    refresh(row);
    return row;
  }

  function addExtra(v) {
    v = v || {};
    var row = el(EXTRA_HTML);
    extrasBox.appendChild(row);
    row.querySelector('input[name=extra_amount]').value = v.amount || '';
    row.querySelector('input[name=extra_name]').value = v.name || '';
    return row;
  }

  // ----- mahsulot qatorlari: hodisalar -----
  linesBox.addEventListener('input', function (e) {
    var t = e.target, row;
    if (t.classList.contains('cb-input')) {
      row = t.closest('.row');
      parts(row).hid.value = '';
      refresh(row);
      openDd(row, false);
    }
  });

  linesBox.addEventListener('focusin', function (e) {
    var t = e.target, row;
    if (t.classList.contains('cb-input')) {
      row = t.closest('.row');
      if (!parts(row).hid.value) {
        openDd(row, true);
        if (t.value) { setTimeout(function () { t.select(); }, 0); }
      }
    }
  });

  linesBox.addEventListener('focusout', function (e) {
    var t = e.target, row;
    if (t.classList.contains('cb-input')) {
      row = t.closest('.row');
      setTimeout(function () {
        var p = parts(row), ex;
        closeDd(row);
        if (!p.hid.value) {
          ex = findExact(p.inp.value);
          if (ex) { p.hid.value = ex.sku; p.inp.value = ex.sku; }
        }
        refresh(row);
      }, 150);
    }
  });

  linesBox.addEventListener('mousedown', function (e) {
    var o = e.target.closest ? e.target.closest('.opt') : null, row;
    if (!o || o.classList.contains('empty')) { return; }
    e.preventDefault();
    row = o.closest('.row');
    if (active && active.row === row) {
      choose(row, o.hasAttribute('data-new') ? 'new' : parseInt(o.getAttribute('data-i'), 10));
    }
  });

  linesBox.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('button.x') : null;
    if (b) { b.closest('.row').remove(); active = null; }
  });

  linesBox.addEventListener('keydown', function (e) {
    var t = e.target, row = t.closest ? t.closest('.row') : null, opts, o, next;
    if (!row) { return; }
    if (t.classList.contains('cb-input')) {
      opts = optionNodes(row);
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!active || active.row !== row) { openDd(row, false); return; }
        if (!opts.length) { return; }
        active.idx = (active.idx + (e.key === 'ArrowDown' ? 1 : -1) + opts.length) % opts.length;
        paint();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (active && active.row === row && active.idx >= 0 && opts[active.idx]) {
          o = opts[active.idx];
          choose(row, o.hasAttribute('data-new') ? 'new' : parseInt(o.getAttribute('data-i'), 10));
        } else {
          row.querySelector('input[name=line_qty]').focus();
        }
      } else if (e.key === 'Escape') {
        closeDd(row);
      }
    } else if (e.key === 'Enter' && (t.name === 'line_qty' || t.name === 'line_cny')) {
      e.preventDefault();
      next = row.nextElementSibling || addLine();
      next.querySelector('.cb-input').focus();
    }
  });

  document.getElementById('add-line').addEventListener('click', function () {
    addLine().querySelector('.cb-input').focus();
  });

  perPrice.addEventListener('change', function () {
    var cs = linesBox.querySelectorAll('input[name=line_cny]'), i;
    linesBox.classList.toggle('pricing', perPrice.checked);
    if (!perPrice.checked) { for (i = 0; i < cs.length; i++) { cs[i].value = ''; } }
  });

  // do'kon almashsa: boshqa do'kon SKU'lari tozalanadi (soni qoladi)
  shopSel.addEventListener('change', function () {
    var rows = linesBox.querySelectorAll('.row.line'), i, p;
    for (i = 0; i < rows.length; i++) {
      p = parts(rows[i]);
      if (p.hid.value && !findExact(p.hid.value)) { p.hid.value = ''; p.inp.value = ''; }
      refresh(rows[i]);
    }
  });

  // ----- qo'shimcha chiqimlar -----
  document.getElementById('add-extra').addEventListener('click', function () {
    addExtra().querySelector('input[name=extra_amount]').focus();
  });

  extrasBox.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('button.x') : null;
    if (b) { b.closest('.row').remove(); }
  });

  extrasBox.addEventListener('keydown', function (e) {
    var t = e.target, row = t.closest ? t.closest('.row') : null, next;
    if (!row || e.key !== 'Enter') { return; }
    e.preventDefault();
    if (t.name === 'extra_amount') { row.querySelector('input[name=extra_name]').focus(); return; }
    if (t.name === 'extra_name' && row.querySelector('input[name=extra_amount]').value.trim()) {
      next = row.nextElementSibling || addExtra();
      next.querySelector('input[name=extra_amount]').focus();
    }
  });

  // ----- Markaziy bank kursi -----
  function wireRate(btnId, ccy, rateId, dateFn, noteId) {
    var btn = document.getElementById(btnId);
    if (!btn) { return; }
    btn.addEventListener('click', function () {
      var note = document.getElementById(noteId), date = dateFn();
      note.textContent = 'Markaziy bank kursi olinmoqda...';
      fetch('/api/rate?ccy=' + ccy + '&date=' + encodeURIComponent(date))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.ok) {
            document.getElementById(rateId).value = String(d.rate);
            note.textContent = 'Markaziy bank kursi (' + d.date + '): 1 ' + ccy + ' = ' + d.rate +
              " so'm. " + (d.warn ? d.warn + ' ' : '') + "Sizning kursingiz boshqacha bo'lsa, o'zgartiring.";
          } else {
            note.textContent = "Kursni olib bo'lmadi: " + ((d && d.error) || "noma'lum xato") + ". Qo'lda yozing.";
          }
        })
        .catch(function () { note.textContent = "Kursni olib bo'lmadi (tarmoq xatosi). Qo'lda yozing."; });
    });
  }
  wireRate('fetch-cny', 'CNY', 'cny_rate', function () { return document.getElementById('date').value; }, 'note-cny');
  wireRate('fetch-usd', 'USD', 'usd_rate', function () {
    return document.getElementById('cargo_date').value || document.getElementById('date').value;
  }, 'note-usd');

  // ----- yuborish -----
  form.addEventListener('keydown', function (e) {   // tasodifiy Enter formani yubormasin
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && !e.defaultPrevented) { e.preventDefault(); }
  });
  form.addEventListener('submit', function () {
    var b = form.querySelector('button.save');
    if (b) { b.disabled = true; b.textContent = 'Saqlanmoqda...'; }
  });
  window.addEventListener('pageshow', function () {
    var b = form.querySelector('button.save');
    if (b) { b.disabled = false; b.textContent = 'Saqlash'; }
  });

  // ----- boshlang'ich holat -----
  var L = initial.lines || [], X = initial.extras || [], i, anyPrice = false;
  for (i = 0; i < L.length; i++) { addLine(L[i]); if (L[i].cny) { anyPrice = true; } }
  if (!L.length) { addLine(); }
  for (i = 0; i < X.length; i++) { addExtra(X[i]); }
  perPrice.checked = anyPrice || !!initial.per_price;
  linesBox.classList.toggle('pricing', perPrice.checked);

  (function focusHash() {
    var h = (root.location.hash || '').replace('#', ''), sec = h ? document.getElementById(h) : null, t;
    if (!sec) { return; }
    sec.scrollIntoView();
    if (h === 'lines-sec') {
      t = linesBox.querySelector('.row.free .cb-input') || linesBox.querySelector('.cb-input');
    } else {
      t = sec.querySelector('input');
    }
    if (t) { t.focus(); }
  })();
})(typeof window !== 'undefined' ? window : this);
