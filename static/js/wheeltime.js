/* ===========================================================================
   Барабанный выбор времени (iOS-style) для <input type="time">.
   Два колеса — часы (00–23) и минуты (шаг 5). Прокрутка пальцем, колесом мыши
   и перетягиванием; снап к ближайшему значению; центральная полоса выбора.
   Оригинальный input прячется, значение H:i пишется обратно в него (для формы).
   ======================================================================== */
(function () {
  "use strict";
  var ITEM = 40;        // высота строки, px (синхронно с CSS)
  var VISIBLE = 5;      // сколько строк видно (нечётное — центр по середине)
  var PAD = ITEM * ((VISIBLE - 1) / 2);
  var STEP = 5;         // шаг минут

  function pad(n) { return ("0" + n).slice(-2); }
  function range(n, step) {
    var out = [];
    for (var i = 0; i < n; i += (step || 1)) out.push(i);
    return out;
  }

  var HOURS = range(24, 1);
  var MINS = range(60, STEP);

  function nearestMin(m) {
    return Math.round(m / STEP) * STEP % 60;
  }

  function parseValue(v) {
    var m = /^(\d{1,2}):(\d{2})$/.exec(v || "");
    if (m) return { h: Math.min(23, +m[1]), m: nearestMin(+m[2]) };
    var now = new Date();
    return { h: now.getHours(), m: nearestMin(now.getMinutes()) };
  }

  function buildColumn(values, unit) {
    var col = document.createElement("div");
    col.className = "wtime-col";
    col.dataset.unit = unit;
    values.forEach(function (v) {
      var it = document.createElement("div");
      it.className = "wtime-item";
      it.textContent = pad(v);
      it.dataset.val = v;
      col.appendChild(it);
    });
    return col;
  }

  // Индекс выбранного значения по позиции скролла
  function selectedIndex(col) {
    return Math.round(col.scrollTop / ITEM);
  }
  function scrollToIndex(col, idx) {
    col.scrollTop = idx * ITEM;
    markCentered(col);
  }
  function markCentered(col) {
    var idx = selectedIndex(col);
    var items = col.children;
    for (var i = 0; i < items.length; i++) {
      items[i].classList.toggle("on", i === idx);
    }
  }

  // Перетягивание мышью (на тач работает нативный скролл).
  // Захват указателя — ТОЛЬКО когда реально потащили, иначе клик по цифре не проходит.
  function enableDrag(col) {
    var down = false, startY = 0, startTop = 0, moved = false, pid = null;
    col.addEventListener("pointerdown", function (e) {
      if (e.pointerType === "touch") return; // тач — нативно
      down = true; moved = false; startY = e.clientY; startTop = col.scrollTop; pid = e.pointerId;
    });
    col.addEventListener("pointermove", function (e) {
      if (!down) return;
      if (!moved) {
        if (Math.abs(e.clientY - startY) < 4) return; // это ещё клик, не тащим
        moved = true;
        try { col.setPointerCapture(pid); } catch (_) {}
      }
      col.scrollTop = startTop - (e.clientY - startY);
      markCentered(col);
    });
    function up() {
      if (!down) return;
      down = false;
      if (moved) scrollToIndex(col, selectedIndex(col)); // тащили — доводим до строки
      // если не тащили — ничего не делаем, сработает click по цифре
    }
    col.addEventListener("pointerup", up);
    col.addEventListener("pointercancel", up);
  }

  var openPop = null;
  function close() {
    if (openPop) { openPop.remove(); openPop = null; }
  }

  function openFor(input, field) {
    close();
    var cur = parseValue(input.value);

    var back = document.createElement("div");
    back.className = "wtime-backdrop";

    var pop = document.createElement("div");
    pop.className = "wtime-pop";
    pop.innerHTML =
      '<div class="wtime-title">Время</div>' +
      '<div class="wtime-wheels">' +
        '<div class="wtime-band"></div>' +
      '</div>' +
      '<div class="wtime-actions">' +
        '<button type="button" class="btn wtime-cancel">Отмена</button>' +
        '<button type="button" class="btn primary wtime-ok">Готово</button>' +
      '</div>';

    var wheels = pop.querySelector(".wtime-wheels");
    var colH = buildColumn(HOURS, "h");
    var sep = document.createElement("div"); sep.className = "wtime-sep"; sep.textContent = ":";
    var colM = buildColumn(MINS, "m");
    wheels.appendChild(colH); wheels.appendChild(sep); wheels.appendChild(colM);

    back.appendChild(pop);
    document.body.appendChild(back);
    openPop = back;

    // Позиционируем у поля (как выпадашка), а не по центру экрана
    (function place() {
      var r = field.getBoundingClientRect();
      var popW = pop.offsetWidth, popH = pop.offsetHeight;
      var margin = 8;
      var top = r.bottom + 6;
      if (top + popH > window.innerHeight - margin) {
        var above = r.top - popH - 6;
        top = above >= margin ? above : Math.max(margin, window.innerHeight - popH - margin);
      }
      var left = r.left;
      if (left + popW > window.innerWidth - margin) left = window.innerWidth - popW - margin;
      if (left < margin) left = margin;
      pop.style.top = Math.round(top) + "px";
      pop.style.left = Math.round(left) + "px";
    })();

    // Снап по завершении прокрутки (тач/колесо)
    [colH, colM].forEach(function (col) {
      var t = null;
      col.addEventListener("scroll", function () {
        markCentered(col);
        clearTimeout(t);
        t = setTimeout(function () { scrollToIndex(col, selectedIndex(col)); }, 90);
      });
      // Клик по цифре — плавно доводим её в центр
      Array.prototype.forEach.call(col.children, function (it, i) {
        it.addEventListener("click", function () {
          col.scrollTo({ top: i * ITEM, behavior: "smooth" });
        });
      });
      enableDrag(col);
    });

    // Начальные позиции (после вставки в DOM)
    scrollToIndex(colH, HOURS.indexOf(cur.h));
    scrollToIndex(colM, MINS.indexOf(cur.m));

    function commit() {
      var h = HOURS[selectedIndex(colH)];
      var m = MINS[selectedIndex(colM)];
      var val = pad(h) + ":" + pad(m);
      input.value = val;
      field.textContent = val;
      field.classList.add("filled");
      input.dispatchEvent(new Event("change", { bubbles: true }));
      close();
    }

    pop.querySelector(".wtime-ok").addEventListener("click", commit);
    pop.querySelector(".wtime-cancel").addEventListener("click", close);
    back.addEventListener("click", function (e) { if (e.target === back) close(); });
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
    });
  }

  function enhance(input) {
    if (input.dataset.wtime) return;
    input.dataset.wtime = "1";
    input.style.display = "none";

    var field = document.createElement("div");
    field.className = "wtime-field";
    field.tabIndex = 0;
    var v = input.value;
    if (v) { field.textContent = v; field.classList.add("filled"); }
    else { field.innerHTML = '<span class="wtime-ph">--:--</span>'; }

    input.parentNode.insertBefore(field, input.nextSibling);
    field.addEventListener("click", function () { openFor(input, field); });
    field.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openFor(input, field); }
    });
  }

  function init() {
    document.querySelectorAll('input[type="time"]').forEach(enhance);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  window.WheelTime = { init: init };
})();
