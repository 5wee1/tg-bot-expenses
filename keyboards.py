from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import PRO_STARS


def main_menu(is_pro: bool = False):
    kb = InlineKeyboardBuilder()
    kb.button(text="➖ Расход", callback_data="add:expense")
    kb.button(text="➕ Доход", callback_data="add:income")
    kb.button(text="📊 Статистика", callback_data="stats:menu")
    kb.button(text="🗂 Категории", callback_data="cats:menu")
    kb.button(text="🕘 Последние", callback_data="recent")
    if not is_pro:
        kb.button(text="⭐ Про", callback_data="pro:info")
        kb.adjust(2, 2, 2)
    else:
        kb.adjust(2, 2, 1)
    return kb.as_markup()


def cancel_only_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="menu")
    return kb.as_markup()


def categories_kb(categories):
    kb = InlineKeyboardBuilder()
    for cat in categories:
        kb.button(text=f"{cat['emoji']} {cat['name']}", callback_data=f"pick:{cat['id']}")
    kb.button(text="❌ Отмена", callback_data="menu")
    kb.adjust(2)
    return kb.as_markup()


def after_add_kb(transaction_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Отменить", callback_data=f"undo:{transaction_id}")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(2)
    return kb.as_markup()


def stats_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Сегодня", callback_data="stats:today")
    kb.button(text="🗓 Неделя", callback_data="stats:week")
    kb.button(text="📆 Месяц", callback_data="stats:month")
    kb.button(text="♾ Всё время", callback_data="stats:all")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def cats_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить", callback_data="cats:add")
    kb.button(text="🗑 Удалить", callback_data="cats:del")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(2, 1)
    return kb.as_markup()


def cats_type_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➖ Расход", callback_data="cats:addt:expense")
    kb.button(text="➕ Доход", callback_data="cats:addt:income")
    kb.button(text="❌ Отмена", callback_data="cats:menu")
    kb.adjust(2, 1)
    return kb.as_markup()


def cats_delete_kb(categories):
    kb = InlineKeyboardBuilder()
    for cat in categories:
        label = "расход" if cat["type"] == "expense" else "доход"
        kb.button(
            text=f"🗑 {cat['emoji']} {cat['name']} ({label})",
            callback_data=f"catdel:{cat['id']}",
        )
    kb.button(text="↩️ Назад", callback_data="cats:menu")
    kb.adjust(1)
    return kb.as_markup()


def recent_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Меню", callback_data="menu")
    return kb.as_markup()


def pro_info_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text=f"💳 Купить за {PRO_STARS} ⭐", callback_data="pro:buy")
    kb.button(text="❌ Отмена", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()
