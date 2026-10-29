"""
Шаблонные теги ядра: проверка права и вывод подсказки.
"""
from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape

from core.permissions import has_perm as _has_perm
from core.hints import get_hint

register = template.Library()


# --- {% if request.user|can:"appointment.create" %} ... ---
@register.filter(name="can")
def can(user, code):
    """Фильтр: есть ли у пользователя право. Для скрытия кнопок в UI.
    ВАЖНО: это только UI; действие всё равно защищено @requires на сервере."""
    return _has_perm(user, code)


# --- {{ 125000|money }} → «125 000» (разряды пробелом, по-русски) ---
@register.filter(name="money")
def money(value):
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return value
    return f"{n:,}".replace(",", " ")


# --- {% hint "key" %} — значок подсказки, если у пользователя включён показ ---
@register.simple_tag(takes_context=True)
def hint(context, key):
    # Показываем подсказки только если включено в профиле
    if not context.get("show_hints"):
        return ""
    text = get_hint(key)
    if not text:
        return ""
    # Значок "?" с текстом в title (hover) и data-hint (для долгого тапа на тач)
    html = (
        f'<span class="hint" tabindex="0" role="button" aria-label="Подсказка" '
        f'title="{escape(text)}" data-hint="{escape(text)}">?</span>'
    )
    return mark_safe(html)
