import csv
import io

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile, CallbackQuery, LabeledPrice, Message, PreCheckoutQuery,
)

import database as db
import keyboards as kb
from config import CURRENCY, PRO_STARS
from utils import format_money

router = Router()


class States(StatesGroup):
    waiting_tx = State()
    waiting_category = State()
    auto_saved = State()
    waiting_new_category = State()
    waiting_budget_amount = State()
    waiting_recurring_tx = State()
    waiting_recurring_cat = State()
    waiting_recurring_day = State()


def parse_input(text: str):
    text = (text or "").strip()
    if not text:
        return None
    parts = text.rsplit(maxsplit=1)
    if len(parts) == 1:
        try:
            return "", float(parts[0].replace(",", "."))
        except ValueError:
            return None
    comment, amount_str = parts
    try:
        return comment.strip(), float(amount_str.replace(",", "."))
    except ValueError:
        return None


def budget_warning(user_id: int, category_id: int, tx_type: str) -> str:
    if tx_type != "expense":
        return ""
    info = db.check_budget_status(user_id, category_id)
    if not info:
        return ""
    spent, limit = info["spent"], info["monthly_limit"]
    pct = (spent / limit * 100) if limit > 0 else 0
    if pct >= 100:
        return f"🚨 Лимит превышен! {format_money(spent)} / {format_money(limit)} {CURRENCY}"
    if pct >= 80:
        return f"⚠️ {pct:.0f}% лимита: {format_money(spent)} / {format_money(limit)} {CURRENCY}"
    return ""


async def safe_edit(message, text, **kwargs):
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest:
        await message.answer(text, **kwargs)


# ---------- Start / Menu ----------

@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(
        "Привет! Я бот для учёта расходов и доходов.\n\n"
        "Нажми кнопку, выбери тип операции, напиши <code>название сумма</code> "
        "(например <code>кофе 300</code>) и выбери категорию.",
        reply_markup=kb.main_menu(is_pro=db.is_pro(msg.from_user.id)),
    )


@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "<b>Как пользоваться</b>\n\n"
        "1. Нажми <b>➖ Расход</b> или <b>➕ Доход</b>\n"
        "2. Пришли сообщение в формате <code>название сумма</code>\n"
        "   Например: <code>кофе 300</code> или <code>такси 1500</code>\n"
        "3. Выбери категорию из кнопок\n\n"
        "В разделе <b>🗂 Категории</b> можно добавлять и удалять свои категории.\n"
        "В разделе <b>📊 Статистика</b> — суммы по категориям за разные периоды.",
        reply_markup=kb.main_menu(is_pro=db.is_pro(msg.from_user.id)),
    )


@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(
        cb.message,
        "Главное меню. Выбери действие:",
        reply_markup=kb.main_menu(is_pro=db.is_pro(cb.from_user.id)),
    )
    await cb.answer()


# ---------- Add transaction ----------

@router.callback_query(F.data.startswith("add:"))
async def cb_add(cb: CallbackQuery, state: FSMContext):
    type_ = cb.data.split(":")[1]
    await state.set_state(States.waiting_tx)
    await state.update_data(tx_type=type_)
    label = "расход" if type_ == "expense" else "доход"
    await safe_edit(
        cb.message,
        f"Введи {label} сообщением в формате:\n"
        f"<code>название сумма</code>\n\n"
        f"Примеры:\n<code>кофе 300</code>\n<code>такси 1500</code>\n<code>зарплата 80000</code>",
        reply_markup=kb.cancel_only_kb(),
    )
    await cb.answer()


@router.message(States.waiting_tx)
async def handle_tx_input(msg: Message, state: FSMContext):
    parsed = parse_input(msg.text)
    if parsed is None:
        await msg.answer(
            "Не понял. Формат: <code>название сумма</code>\nНапример: <code>кофе 300</code>",
            reply_markup=kb.cancel_only_kb(),
        )
        return
    comment, amount = parsed
    if amount <= 0:
        await msg.answer("Сумма должна быть больше нуля.")
        return
    data = await state.get_data()
    type_ = data["tx_type"]

    # Auto-categorization
    if comment:
        auto_cat_id = db.get_auto_category(msg.from_user.id, comment, type_)
        if auto_cat_id:
            cat = db.get_category(auto_cat_id)
            tx_id = db.add_transaction(msg.from_user.id, auto_cat_id, type_, amount, comment)
            db.update_autocategory(msg.from_user.id, comment, auto_cat_id)
            warn = budget_warning(msg.from_user.id, auto_cat_id, type_)
            sign = "−" if type_ == "expense" else "+"
            await state.set_state(States.auto_saved)
            await state.update_data(auto_tx_id=tx_id, auto_comment=comment, auto_amount=amount, auto_type=type_)
            await msg.answer(
                f"🎯 Записано\n\n"
                f"{cat['emoji']} <b>{cat['name']}</b>\n"
                f"<b>{sign} {format_money(amount)} {CURRENCY}</b>"
                + (f"\n📝 {comment}" if comment else "")
                + (f"\n\n{warn}" if warn else ""),
                reply_markup=kb.after_add_auto_kb(tx_id),
            )
            return

    await state.update_data(comment=comment, amount=amount)
    await state.set_state(States.waiting_category)
    cats = db.get_categories(msg.from_user.id, type_)
    label = "расход" if type_ == "expense" else "доход"
    title = comment if comment else "(без названия)"
    await msg.answer(
        f"📝 {label.capitalize()}: <b>{title}</b> — <b>{format_money(amount)} {CURRENCY}</b>\n\n"
        f"Выбери категорию:",
        reply_markup=kb.categories_kb(cats),
    )


@router.callback_query(States.waiting_category, F.data.startswith("pick:"))
async def cb_pick_category(cb: CallbackQuery, state: FSMContext):
    cat_id = int(cb.data.split(":")[1])
    data = await state.get_data()
    type_ = data.get("tx_type")
    comment = data.get("comment", "")
    amount = data.get("amount", 0.0)
    cat = db.get_category(cat_id)
    if not cat or cat["type"] != type_:
        await cb.answer("Категория не найдена", show_alert=True)
        return
    tx_id = db.add_transaction(cb.from_user.id, cat_id, type_, amount, comment)
    db.update_autocategory(cb.from_user.id, comment, cat_id)
    warn = budget_warning(cb.from_user.id, cat_id, type_)
    await state.clear()
    sign = "−" if type_ == "expense" else "+"
    await safe_edit(
        cb.message,
        f"✅ Записано\n\n"
        f"{cat['emoji']} <b>{cat['name']}</b>\n"
        f"<b>{sign} {format_money(amount)} {CURRENCY}</b>"
        + (f"\n📝 {comment}" if comment else "")
        + (f"\n\n{warn}" if warn else ""),
        reply_markup=kb.after_add_kb(tx_id),
    )
    await cb.answer("Сохранено")


@router.message(States.waiting_category)
async def handle_wrong_state_msg(msg: Message):
    await msg.answer("Выбери категорию кнопкой ниже или нажми «❌ Отмена».")


@router.callback_query(States.auto_saved, F.data == "autochange")
async def cb_auto_change(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db.delete_transaction(cb.from_user.id, data["auto_tx_id"])
    db.reset_autocategory(cb.from_user.id, data["auto_comment"])
    await state.set_state(States.waiting_category)
    await state.update_data(tx_type=data["auto_type"], comment=data["auto_comment"], amount=data["auto_amount"])
    cats = db.get_categories(cb.from_user.id, data["auto_type"])
    await safe_edit(cb.message, "Выбери категорию:", reply_markup=kb.categories_kb(cats))
    await cb.answer()


@router.callback_query(F.data.startswith("undo:"))
async def cb_undo(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    tx_id = int(cb.data.split(":")[1])
    ok = db.delete_transaction(cb.from_user.id, tx_id)
    if ok:
        await safe_edit(
            cb.message,
            "↩️ Транзакция отменена.",
            reply_markup=kb.main_menu(is_pro=db.is_pro(cb.from_user.id)),
        )
        await cb.answer("Удалено")
    else:
        await cb.answer("Уже не существует", show_alert=True)


# ---------- Stats ----------

@router.callback_query(F.data == "stats:menu")
async def cb_stats_menu(cb: CallbackQuery):
    await safe_edit(cb.message, "📊 За какой период показать статистику?", reply_markup=kb.stats_menu_kb())
    await cb.answer()


@router.callback_query(F.data.in_({"stats:today", "stats:week", "stats:month", "stats:all"}))
async def cb_stats_period(cb: CallbackQuery):
    period = cb.data.split(":")[1]
    stats = db.get_stats(cb.from_user.id, period)
    titles = {"today": "Сегодня", "week": "Неделя", "month": "Месяц", "all": "Всё время"}

    expenses = [s for s in stats if s["type"] == "expense"]
    incomes = [s for s in stats if s["type"] == "income"]
    lines = [f"📊 <b>{titles[period]}</b>"]

    if incomes:
        lines.append(f"\n<b>➕ Доходы: {format_money(sum(s['total'] for s in incomes))} {CURRENCY}</b>")
        for s in incomes:
            lines.append(f"  {s['emoji']} {s['name']}: {format_money(s['total'])} {CURRENCY}")
    if expenses:
        lines.append(f"\n<b>➖ Расходы: {format_money(sum(s['total'] for s in expenses))} {CURRENCY}</b>")
        for s in expenses:
            lines.append(f"  {s['emoji']} {s['name']}: {format_money(s['total'])} {CURRENCY}")
    if incomes and expenses:
        balance = sum(s["total"] for s in incomes) - sum(s["total"] for s in expenses)
        sign = "+" if balance >= 0 else "−"
        lines.append(f"\n<b>💼 Баланс: {sign}{format_money(abs(balance))} {CURRENCY}</b>")
    if not stats:
        lines.append("\nНет записей за этот период.")

    await safe_edit(cb.message, "\n".join(lines), reply_markup=kb.stats_menu_kb())
    await cb.answer()


# ---------- Recent ----------

@router.callback_query(F.data == "recent")
async def cb_recent(cb: CallbackQuery):
    items = db.get_recent(cb.from_user.id, 10)
    if not items:
        text = "🕘 Пока нет записей."
    else:
        lines = ["🕘 <b>Последние операции</b>\n"]
        for it in items:
            sign = "−" if it["type"] == "expense" else "+"
            cmt = f" — {it['comment']}" if it["comment"] else ""
            lines.append(
                f"{it['created_at'][:16]}  {it['emoji']} {it['name']}{cmt}\n"
                f"  <b>{sign} {format_money(it['amount'])} {CURRENCY}</b>"
            )
        text = "\n".join(lines)
    await safe_edit(cb.message, text, reply_markup=kb.recent_kb())
    await cb.answer()


# ---------- Categories ----------

def _render_cats_overview(user_id: int) -> str:
    user_cats = db.get_user_categories(user_id)
    if not user_cats:
        return (
            "🗂 <b>Категории</b>\n\n"
            "У тебя нет своих категорий — используются базовые.\n"
            "Нажми <b>➕ Добавить</b>, чтобы создать новую."
        )
    lines = ["🗂 <b>Твои категории</b>\n"]
    exp = [c for c in user_cats if c["type"] == "expense"]
    inc = [c for c in user_cats if c["type"] == "income"]
    if exp:
        lines.append("<b>Расходы:</b>")
        lines += [f"  {c['emoji']} {c['name']}" for c in exp]
    if inc:
        if exp:
            lines.append("")
        lines.append("<b>Доходы:</b>")
        lines += [f"  {c['emoji']} {c['name']}" for c in inc]
    return "\n".join(lines)


@router.callback_query(F.data == "cats:menu")
async def cb_cats_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(cb.message, _render_cats_overview(cb.from_user.id), reply_markup=kb.cats_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "cats:add")
async def cb_cats_add(cb: CallbackQuery):
    await safe_edit(cb.message, "Для чего новая категория?", reply_markup=kb.cats_type_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("cats:addt:"))
async def cb_cats_add_type(cb: CallbackQuery, state: FSMContext):
    type_ = cb.data.split(":")[2]
    await state.set_state(States.waiting_new_category)
    await state.update_data(cat_type=type_)
    await safe_edit(
        cb.message,
        "Пришли эмодзи и название новой категории одним сообщением.\n\n"
        "Например: <code>🐱 Котик</code> или <code>🎸 Хобби</code>",
        reply_markup=kb.cancel_only_kb(),
    )
    await cb.answer()


@router.message(States.waiting_new_category)
async def handle_new_category(msg: Message, state: FSMContext):
    parts = (msg.text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("Формат: <code>эмодзи название</code>\nНапример: <code>🐱 Котик</code>", reply_markup=kb.cancel_only_kb())
        return
    emoji, name = parts[0], parts[1].strip()
    if len(name) > 40:
        await msg.answer("Название слишком длинное (максимум 40 символов).")
        return
    data = await state.get_data()
    db.add_category(msg.from_user.id, data["cat_type"], emoji, name)
    await state.clear()
    label = "расходов" if data["cat_type"] == "expense" else "доходов"
    await msg.answer(f"✅ Категория <b>{emoji} {name}</b> добавлена в {label}.", reply_markup=kb.main_menu(is_pro=db.is_pro(msg.from_user.id)))


@router.callback_query(F.data == "cats:del")
async def cb_cats_del(cb: CallbackQuery):
    cats = db.get_user_categories(cb.from_user.id)
    if not cats:
        await cb.answer("У тебя нет своих категорий", show_alert=True)
        return
    await safe_edit(
        cb.message,
        "Выбери категорию для удаления.\n<i>Записи с этой категорией удалены не будут.</i>",
        reply_markup=kb.cats_delete_kb(cats),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("catdel:"))
async def cb_cat_delete(cb: CallbackQuery):
    cat_id = int(cb.data.split(":")[1])
    if not db.delete_category(cb.from_user.id, cat_id):
        await cb.answer("Не удалось удалить", show_alert=True)
        return
    await cb.answer("Удалено")
    cats = db.get_user_categories(cb.from_user.id)
    if cats:
        await safe_edit(
            cb.message,
            "Выбери категорию для удаления.\n<i>Записи с этой категорией удалены не будут.</i>",
            reply_markup=kb.cats_delete_kb(cats),
        )
    else:
        await safe_edit(cb.message, _render_cats_overview(cb.from_user.id), reply_markup=kb.cats_menu_kb())


# ---------- Pro ----------

@router.callback_query(F.data == "pro:info")
async def cb_pro_info(cb: CallbackQuery):
    if db.is_pro(cb.from_user.id):
        await cb.answer()
        return
    await safe_edit(
        cb.message,
        f"⭐ <b>Поддержать разработку</b>\n\nОдноразовый платёж — <b>{PRO_STARS} звезда Telegram</b>.",
        reply_markup=kb.pro_info_kb(),
    )
    await cb.answer()


@router.callback_query(F.data == "pro:buy")
async def cb_pro_buy(cb: CallbackQuery, bot: Bot):
    if db.is_pro(cb.from_user.id):
        await cb.answer()
        return
    await bot.send_invoice(
        chat_id=cb.from_user.id,
        title="⭐ Поддержать разработку",
        description=f"Одноразовый платёж — {PRO_STARS} звезда Telegram",
        payload="pro_purchase",
        currency="XTR",
        prices=[LabeledPrice(label="Поддержать", amount=PRO_STARS)],
        provider_token="",
    )
    await cb.answer()


@router.pre_checkout_query()
async def pre_checkout_handler(pq: PreCheckoutQuery):
    await pq.answer(ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(msg: Message):
    if msg.successful_payment.invoice_payload == "pro_purchase":
        db.add_pro_user(msg.from_user.id)
        await msg.answer("✅ Спасибо!", reply_markup=kb.main_menu(is_pro=True))


# ---------- Export ----------

@router.callback_query(F.data == "export")
async def cb_export(cb: CallbackQuery, bot: Bot):
    transactions = db.get_all_transactions(cb.from_user.id)
    if not transactions:
        await cb.answer("Нет данных для экспорта", show_alert=True)
        return
    await cb.answer("Генерирую файл...")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Дата", "Тип", "Категория", "Сумма", "Комментарий"])
    for tx in transactions:
        writer.writerow([
            tx["created_at"],
            "Расход" if tx["type"] == "expense" else "Доход",
            f"{tx['emoji']} {tx['name']}",
            tx["amount"],
            tx["comment"] or "",
        ])
    file = BufferedInputFile(output.getvalue().encode("utf-8-sig"), filename="expenses.csv")
    await bot.send_document(
        cb.from_user.id,
        file,
        caption=f"📤 Экспорт — {len(transactions)} записей",
    )


# ---------- Budget limits ----------

def _render_budgets(user_id: int) -> str:
    budgets = db.get_budgets(user_id)
    if not budgets:
        return "💰 <b>Лимиты</b>\n\nУ тебя пока нет лимитов по категориям.\nНажми <b>➕ Добавить лимит</b>."
    lines = ["💰 <b>Лимиты на этот месяц</b>\n"]
    for b in budgets:
        spent, limit = b["spent"], b["monthly_limit"]
        pct = int(spent / limit * 100) if limit > 0 else 0
        warn = " 🚨" if pct >= 100 else (" ⚠️" if pct >= 80 else "")
        lines.append(f"{b['emoji']} {b['name']}: {format_money(spent)} / {format_money(limit)} {CURRENCY} ({pct}%){warn}")
    return "\n".join(lines)


@router.callback_query(F.data == "budget:menu")
async def cb_budget_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    budgets = db.get_budgets(cb.from_user.id)
    await safe_edit(cb.message, _render_budgets(cb.from_user.id),
                    reply_markup=kb.budget_menu_kb(budgets) if budgets else kb.budget_menu_empty_kb())
    await cb.answer()


@router.callback_query(F.data == "budget:add")
async def cb_budget_add(cb: CallbackQuery):
    cats = db.get_categories(cb.from_user.id, "expense")
    await safe_edit(cb.message, "Выбери категорию для лимита:", reply_markup=kb.budget_cat_kb(cats))
    await cb.answer()


@router.callback_query(F.data.startswith("bpick:"))
async def cb_budget_cat(cb: CallbackQuery, state: FSMContext):
    cat_id = int(cb.data.split(":")[1])
    cat = db.get_category(cat_id)
    await state.set_state(States.waiting_budget_amount)
    await state.update_data(budget_cat_id=cat_id)
    await safe_edit(
        cb.message,
        f"Введи месячный лимит для категории <b>{cat['emoji']} {cat['name']}</b> в рублях:\n\n"
        f"Например: <code>15000</code>",
        reply_markup=kb.cancel_only_kb(),
    )
    await cb.answer()


@router.message(States.waiting_budget_amount)
async def handle_budget_amount(msg: Message, state: FSMContext):
    try:
        amount = float((msg.text or "").strip().replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("Введи число больше нуля. Например: <code>15000</code>", reply_markup=kb.cancel_only_kb())
        return
    data = await state.get_data()
    cat = db.get_category(data["budget_cat_id"])
    db.set_budget(msg.from_user.id, data["budget_cat_id"], amount)
    await state.clear()
    await msg.answer(
        f"✅ Лимит для <b>{cat['emoji']} {cat['name']}</b> — <b>{format_money(amount)} {CURRENCY}/мес</b>.",
        reply_markup=kb.main_menu(is_pro=True),
    )


@router.callback_query(F.data.startswith("budget:del:"))
async def cb_budget_del(cb: CallbackQuery):
    cat_id = int(cb.data.split(":")[2])
    cat = db.get_category(cat_id)
    db.delete_budget(cb.from_user.id, cat_id)
    await cb.answer(f"Лимит для {cat['name']} удалён")
    budgets = db.get_budgets(cb.from_user.id)
    await safe_edit(cb.message, _render_budgets(cb.from_user.id),
                    reply_markup=kb.budget_menu_kb(budgets) if budgets else kb.budget_menu_empty_kb())


# ---------- Recurring ----------

def _render_recurring(user_id: int) -> str:
    items = db.get_recurring(user_id)
    if not items:
        return "🔁 <b>Регулярные платежи</b>\n\nПока нет регулярных платежей.\nНажми <b>➕ Добавить</b>."
    lines = ["🔁 <b>Регулярные платежи</b>\n"]
    for it in items:
        sign = "➖" if it["type"] == "expense" else "➕"
        name = it["comment"] or it["cat_name"]
        lines.append(f"{it['day_of_month']} числа: {it['emoji']} {name} {sign} {format_money(it['amount'])} {CURRENCY}")
    return "\n".join(lines)


@router.callback_query(F.data == "recur:menu")
async def cb_recur_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    items = db.get_recurring(cb.from_user.id)
    markup = kb.recur_delete_kb(items) if items else kb.recur_menu_kb()
    if items:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Добавить", callback_data="recur:add")
        builder.button(text="🏠 Меню", callback_data="menu")
        for it in items:
            sign = "➖" if it["type"] == "expense" else "➕"
            builder.button(
                text=f"🗑 {it['day_of_month']} числа: {it['emoji']} {it['comment'] or it['cat_name']} {sign}{format_money(it['amount'])}₽",
                callback_data=f"recur:del:{it['id']}",
            )
        builder.adjust(2, 1)
        markup = builder.as_markup()
    await safe_edit(cb.message, _render_recurring(cb.from_user.id), reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data == "recur:add")
async def cb_recur_add(cb: CallbackQuery):
    await safe_edit(cb.message, "Тип регулярного платежа:", reply_markup=kb.recur_type_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("recur:addt:"))
async def cb_recur_type(cb: CallbackQuery, state: FSMContext):
    type_ = cb.data.split(":")[2]
    await state.set_state(States.waiting_recurring_tx)
    await state.update_data(recur_type=type_)
    label = "расход" if type_ == "expense" else "доход"
    await safe_edit(
        cb.message,
        f"Введи регулярный {label} в формате:\n<code>название сумма</code>\n\nНапример: <code>аренда 30000</code>",
        reply_markup=kb.cancel_only_kb(),
    )
    await cb.answer()


@router.message(States.waiting_recurring_tx)
async def handle_recurring_tx(msg: Message, state: FSMContext):
    parsed = parse_input(msg.text)
    if not parsed:
        await msg.answer("Формат: <code>название сумма</code>", reply_markup=kb.cancel_only_kb())
        return
    comment, amount = parsed
    if amount <= 0:
        await msg.answer("Сумма должна быть больше нуля.")
        return
    data = await state.get_data()
    await state.update_data(recur_comment=comment, recur_amount=amount)
    await state.set_state(States.waiting_recurring_cat)
    cats = db.get_categories(msg.from_user.id, data["recur_type"])
    title = comment if comment else "(без названия)"
    await msg.answer(
        f"📝 <b>{title}</b> — <b>{format_money(amount)} {CURRENCY}</b>\n\nВыбери категорию:",
        reply_markup=kb.recur_cat_kb(cats),
    )


@router.callback_query(States.waiting_recurring_cat, F.data.startswith("rpick:"))
async def cb_recurring_cat(cb: CallbackQuery, state: FSMContext):
    cat_id = int(cb.data.split(":")[1])
    await state.update_data(recur_cat_id=cat_id)
    await state.set_state(States.waiting_recurring_day)
    await safe_edit(
        cb.message,
        "В какой день месяца записывать? Введи число от 1 до 28:",
        reply_markup=kb.cancel_only_kb(),
    )
    await cb.answer()


@router.message(States.waiting_recurring_day)
async def handle_recurring_day(msg: Message, state: FSMContext):
    try:
        day = int((msg.text or "").strip())
        if not 1 <= day <= 28:
            raise ValueError
    except ValueError:
        await msg.answer("Введи число от 1 до 28:", reply_markup=kb.cancel_only_kb())
        return
    data = await state.get_data()
    cat = db.get_category(data["recur_cat_id"])
    db.add_recurring(
        msg.from_user.id, data["recur_cat_id"], data["recur_type"],
        data["recur_amount"], data["recur_comment"], day,
    )
    await state.clear()
    sign = "➖" if data["recur_type"] == "expense" else "➕"
    name = data["recur_comment"] or cat["name"]
    await msg.answer(
        f"✅ Добавлено\n\n{cat['emoji']} {name} {sign} {format_money(data['recur_amount'])} {CURRENCY}\n"
        f"Каждый <b>{day}-й</b> день месяца",
        reply_markup=kb.main_menu(is_pro=True),
    )


@router.callback_query(F.data.startswith("recur:del:"))
async def cb_recur_del(cb: CallbackQuery):
    item_id = int(cb.data.split(":")[2])
    db.delete_recurring(cb.from_user.id, item_id)
    await cb.answer("Удалено")
    items = db.get_recurring(cb.from_user.id)
    await safe_edit(cb.message, _render_recurring(cb.from_user.id),
                    reply_markup=kb.recur_menu_kb() if not items else kb.recur_delete_kb(items))


@router.callback_query(F.data.startswith("recur:confirm:"))
async def cb_recur_confirm(cb: CallbackQuery):
    item_id = int(cb.data.split(":")[2])
    item = db.get_recurring_item(item_id)
    if not item:
        await cb.answer("Не найдено", show_alert=True)
        return
    tx_id = db.add_transaction(item["user_id"], item["category_id"], item["type"], item["amount"], item["comment"])
    db.mark_recurring_triggered(item_id)
    sign = "−" if item["type"] == "expense" else "+"
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        f"✅ Записано\n\n{item['emoji']} <b>{item['cat_name']}</b>\n"
        f"<b>{sign} {format_money(item['amount'])} {CURRENCY}</b>",
        reply_markup=kb.after_add_kb(tx_id),
    )
    await cb.answer("Записано")


@router.callback_query(F.data.startswith("recur:skip:"))
async def cb_recur_skip(cb: CallbackQuery):
    item_id = int(cb.data.split(":")[2])
    db.mark_recurring_triggered(item_id)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Пропущено")


# ---------- Fallback ----------

@router.message()
async def fallback(msg: Message):
    await msg.answer(
        "Нажми кнопку <b>➖ Расход</b> или <b>➕ Доход</b>, чтобы начать.",
        reply_markup=kb.main_menu(is_pro=db.is_pro(msg.from_user.id)),
    )
