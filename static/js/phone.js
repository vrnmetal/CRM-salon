/*
 * Единая маска телефона РФ для всех полей ввода номера.
 *
 * Правила:
 *  - +7 появляется автоматически, как только введён первый символ.
 *  - Ведущая «8» или «7» всегда считается кодом страны и заменяется на +7.
 *    Поэтому "8951..." даёт "+7 951...", а НЕ "+7 895..." (8 не попадает в номер).
 *  - "9505555555" → "+7 950 555-55-55".
 *  - На отправке формы значение нормализуется в "+7XXXXXXXXXX" (без пробелов).
 *
 * Навешивается автоматически на input[name*="phone"] и input[type="tel"].
 */
(function () {
  function formatRu(d) {
    // d — национальные цифры (до 10), без кода страны
    var out = "+7";
    if (d.length > 0) out += " " + d.slice(0, 3);
    if (d.length >= 4) out += " " + d.slice(3, 6);
    if (d.length >= 7) out += "-" + d.slice(6, 8);
    if (d.length >= 9) out += "-" + d.slice(8, 10);
    return out;
  }

  function nationalDigits(raw) {
    var digits = (raw || "").replace(/\D/g, "");
    // Ведущие 8 или 7 — это код страны, срезаем (в т.ч. «7» от самого префикса +7)
    if (digits.length && (digits[0] === "8" || digits[0] === "7")) {
      digits = digits.slice(1);
    }
    return digits.slice(0, 10);
  }

  function hasAnyDigit(raw) {
    return /\d/.test(raw || "");
  }

  function onInput(e) {
    var el = e.target;
    if (!hasAnyDigit(el.value)) {
      el.value = "";
      return;
    }
    el.value = formatRu(nationalDigits(el.value));
    // Ввод идёт слева направо — держим курсор в конце
    try {
      el.setSelectionRange(el.value.length, el.value.length);
    } catch (_) {}
  }

  function normalizeForSubmit(el) {
    var d = nationalDigits(el.value);
    el.value = d.length === 10 ? "+7" + d : (el.value || "").replace(/[\s\-]/g, "");
  }

  function attach(el) {
    if (el.__phoneMask) return;
    el.__phoneMask = true;
    el.setAttribute("inputmode", "tel");
    el.setAttribute("autocomplete", "tel");
    if (!el.getAttribute("placeholder")) {
      el.setAttribute("placeholder", "+7 950 123-45-67");
    }
    // Если поле уже предзаполнено (повторный рендер формы) — приводим к виду
    if (hasAnyDigit(el.value)) {
      el.value = formatRu(nationalDigits(el.value));
    }
    el.addEventListener("input", onInput);
    if (el.form) {
      el.form.addEventListener("submit", function () {
        normalizeForSubmit(el);
      });
    }
  }

  function init() {
    var sel = 'input[name*="phone"], input[name*="tel"], input[type="tel"]';
    document.querySelectorAll(sel).forEach(attach);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
