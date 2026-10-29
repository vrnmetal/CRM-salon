"""
Брендирование тенанта: безопасный набор пресетов шрифта.

База нейтральная (системный SF). Тенант может выбрать шрифт из ограниченного
набора — чтобы сохранить премиальность и не сломать вёрстку произвольным шрифтом.
"""

# Пресеты шрифта: код -> (человеку, css font-family)
FONT_PRESETS = {
    "": ("Системный (по умолчанию)",
         "-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif"),
    "rounded": ("Округлый",
                "ui-rounded, 'SF Pro Rounded', 'Segoe UI', system-ui, sans-serif"),
    "grotesk": ("Гротеск",
                "'Inter', 'Helvetica Neue', Arial, sans-serif"),
    "serif": ("С засечками",
              "'Georgia', 'Times New Roman', serif"),
}


def font_stack(code: str) -> str:
    """CSS font-family для пресета (пусто для системного — не переопределяем)."""
    if not code or code not in FONT_PRESETS or code == "":
        return ""
    return FONT_PRESETS[code][1]


def font_choices():
    """Список (код, подпись) для выпадающего списка в настройках."""
    return [(code, label) for code, (label, _) in FONT_PRESETS.items()]
