from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import PRO_STARS
from utils import format_money


def main_menu(is_pro: bool = False):
    kb = InlineKeyboardBuilder()
    kb.button(text="➖ Расход", callback_data="add:expense")
    kb.button(text="➕ Доход", callback_data="add:income")
    kb.button(text="📊 Статистика", callback_data="stats:menu")
    kb.button(text="🗂 Категории", callback_data="cats:menu")
    if is_pro:
        kb.button(text="🕘 Последние", callback_data="recent")
        kb.button(text="📤 Экспорт", callback_data="export")
        kb.button(text="💰 Лимиты", callback_data="budget:menu")
        kb.button(text="🔁 Регулярные", callback_data="recur:menu")
        kb.adjust(2, 2, 2, 2)
    else:
        kb.button(text="🕘 Последние", callback_data="recent")
        kb.button(text="⭐ Про", callback_data="pro:info")
        kb.adjust(2, 2, 2)
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


def after_add_auto_kb(transaction_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Отменить", callback_data=f"undo:{transaction_id}")
    kb.button(text="🔄 Другая кат.", callback_data="autochange")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(2, 1)
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
        kb.button(text=f"🗑 {cat['emoji']} {cat['name']} ({label})", callback_data=f"catdel:{cat['id']}")
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


# ---------- Budget keyboards ----------

def budget_menu_kb(budgets):
    kb = InlineKeyboardBuilder()
    for b in budgets:
        spent = b["spent"]
        limit = b["monthly_limit"]
        pct = int(spent / limit * 100) if limit > 0 else 0
        warn = " ⚠️" if pct >= 80 else ""
        kb.button(
            text=f"🗑 {b['emoji']} {b['name']} ({format_money(spent)}/{format_money(limit)}₽){warn}",
            callback_data=f"budget:del:{b['category_id']}",
        )
    kb.button(text="➕ Добавить лимит", callback_data="budget:add")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def budget_menu_empty_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить лимит", callback_data="budget:add")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def budget_cat_kb(categories):
    kb = InlineKeyboardBuilder()
    for cat in categories:
        kb.button(text=f"{cat['emoji']} {cat['name']}", callback_data=f"bpick:{cat['id']}")
    kb.button(text="❌ Отмена", callback_data="budget:menu")
    kb.adjust(2)
    return kb.as_markup()


# ---------- Recurring keyboards ----------

def recur_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить", callback_data="recur:add")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def recur_type_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➖ Расход", callback_data="recur:addt:expense")
    kb.button(text="➕ Доход", callback_data="recur:addt:income")
    kb.button(text="❌ Отмена", callback_data="recur:menu")
    kb.adjust(2, 1)
    return kb.as_markup()


def recur_cat_kb(categories):
    kb = InlineKeyboardBuilder()
    for cat in categories:
        kb.button(text=f"{cat['emoji']} {cat['name']}", callback_data=f"rpick:{cat['id']}")
    kb.button(text="❌ Отмена", callback_data="recur:menu")
    kb.adjust(2)
    return kb.as_markup()


def recur_delete_kb(items):
    kb = InlineKeyboardBuilder()
    for it in items:
        sign = "➖" if it["type"] == "expense" else "➕"
        kb.button(
            text=f"🗑 {it['day_of_month']} числа: {it['emoji']} {it['comment'] or it['cat_name']} {sign}{format_money(it['amount'])}₽",
            callback_data=f"recur:del:{it['id']}",
        )
    kb.button(text="↩️ Назад", callback_data="recur:menu")
    kb.adjust(1)
    return kb.as_markup()


def recur_reminder_kb(item_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Записать", callback_data=f"recur:confirm:{item_id}")
    kb.button(text="⏭ Пропустить", callback_data=f"recur:skip:{item_id}")
    kb.adjust(2)
    return kb.as_markup()
