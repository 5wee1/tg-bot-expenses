from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

import database as db
import keyboards as kb
from config import CURRENCY, PRO_STARS

router = Router()


class States(StatesGroup):
    waiting_tx = State()
    waiting_category = State()
    waiting_new_category = State()


def parse_input(text: str):
    text = (text or "").strip()
    if not text:
        return None
    parts = text.rsplit(maxsplit=1)
    if len(parts) == 1:
        try:
            amount = float(parts[0].replace(",", "."))
            return "", amount
        except ValueError:
            return None
    comment, amount_str = parts
    try:
        amount = float(amount_str.replace(",", "."))
        return comment.strip(), amount
    except ValueError:
        return None


def format_money(amount: float) -> str:
    if amount == int(amount):
        s = f"{int(amount):,}".replace(",", " ")
    else:
        s = f"{amount:,.2f}".replace(",", " ")
    return s


async def safe_edit(message, text, **kwargs):
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest:
        await message.answer(text, **kwargs)


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
            "Не понял. Формат: <code>название сумма</code>\n"
            "Например: <code>кофе 300</code>",
            reply_markup=kb.cancel_only_kb(),
        )
        return
    comment, amount = parsed
    if amount <= 0:
        await msg.answer("Сумма должна быть больше нуля.")
        return
    data = await state.get_data()
    type_ = data["tx_type"]
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
    await state.clear()
    sign = "−" if type_ == "expense" else "+"
    comment_line = f"\n📝 {comment}" if comment else ""
    await safe_edit(
        cb.message,
        f"✅ Записано\n\n"
        f"{cat['emoji']} <b>{cat['name']}</b>\n"
        f"<b>{sign} {format_money(amount)} {CURRENCY}</b>"
        f"{comment_line}",
        reply_markup=kb.after_add_kb(tx_id),
    )
    await cb.answer("Сохранено")


@router.message(States.waiting_category)
async def handle_wrong_state_msg(msg: Message):
    await msg.answer("Выбери категорию кнопкой ниже или нажми «❌ Отмена».")


@router.callback_query(F.data.startswith("undo:"))
async def cb_undo(cb: CallbackQuery):
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
    await safe_edit(
        cb.message,
        "📊 За какой период показать статистику?",
        reply_markup=kb.stats_menu_kb(),
    )
    await cb.answer()


@router.callback_query(F.data.in_({"stats:today", "stats:week", "stats:month", "stats:all"}))
async def cb_stats_period(cb: CallbackQuery):
    period = cb.data.split(":")[1]
    stats = db.get_stats(cb.from_user.id, period)
    titles = {"today": "Сегодня", "week": "Неделя", "month": "Месяц", "all": "Всё время"}
    title = titles.get(period, period)

    expenses = [s for s in stats if s["type"] == "expense"]
    incomes = [s for s in stats if s["type"] == "income"]

    lines = [f"📊 <b>{title}</b>"]

    if incomes:
        total_in = sum(s["total"] for s in incomes)
        lines.append(f"\n<b>➕ Доходы: {format_money(total_in)} {CURRENCY}</b>")
        for s in incomes:
            lines.append(f"  {s['emoji']} {s['name']}: {format_money(s['total'])} {CURRENCY}")

    if expenses:
        total_out = sum(s["total"] for s in expenses)
        lines.append(f"\n<b>➖ Расходы: {format_money(total_out)} {CURRENCY}</b>")
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
            date = it["created_at"][:16]
            cmt = f" — {it['comment']}" if it["comment"] else ""
            lines.append(
                f"{date}  {it['emoji']} {it['name']}{cmt}\n"
                f"  <b>{sign} {format_money(it['amount'])} {CURRENCY}</b>"
            )
        text = "\n".join(lines)
    await safe_edit(cb.message, text, reply_markup=kb.recent_kb())
    await cb.answer()


# ---------- Categories management ----------

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
        for c in exp:
            lines.append(f"  {c['emoji']} {c['name']}")
    if inc:
        if exp:
            lines.append("")
        lines.append("<b>Доходы:</b>")
        for c in inc:
            lines.append(f"  {c['emoji']} {c['name']}")
    return "\n".join(lines)


@router.callback_query(F.data == "cats:menu")
async def cb_cats_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(cb.message, _render_cats_overview(cb.from_user.id), reply_markup=kb.cats_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "cats:add")
async def cb_cats_add(cb: CallbackQuery):
    await safe_edit(
        cb.message,
        "Для чего новая категория?",
        reply_markup=kb.cats_type_kb(),
    )
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
    text = (msg.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer(
            "Формат: <code>эмодзи название</code>\nНапример: <code>🐱 Котик</code>",
            reply_markup=kb.cancel_only_kb(),
        )
        return
    emoji, name = parts[0], parts[1].strip()
    if len(name) > 40:
        await msg.answer("Название слишком длинное (максимум 40 символов).")
        return
    data = await state.get_data()
    type_ = data["cat_type"]
    db.add_category(msg.from_user.id, type_, emoji, name)
    await state.clear()
    label = "расходов" if type_ == "expense" else "доходов"
    await msg.answer(
        f"✅ Категория <b>{emoji} {name}</b> добавлена в {label}.",
        reply_markup=kb.main_menu(is_pro=db.is_pro(msg.from_user.id)),
    )


@router.callback_query(F.data == "cats:del")
async def cb_cats_del(cb: CallbackQuery):
    cats = db.get_user_categories(cb.from_user.id)
    if not cats:
        await cb.answer("У тебя нет своих категорий", show_alert=True)
        return
    await safe_edit(
        cb.message,
        "Выбери категорию для удаления.\n"
        "<i>Записи с этой категорией удалены не будут.</i>",
        reply_markup=kb.cats_delete_kb(cats),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("catdel:"))
async def cb_cat_delete(cb: CallbackQuery):
    cat_id = int(cb.data.split(":")[1])
    ok = db.delete_category(cb.from_user.id, cat_id)
    if not ok:
        await cb.answer("Не удалось удалить", show_alert=True)
        return
    await cb.answer("Удалено")
    cats = db.get_user_categories(cb.from_user.id)
    if not cats:
        await safe_edit(
            cb.message,
            _render_cats_overview(cb.from_user.id),
            reply_markup=kb.cats_menu_kb(),
        )
    else:
        await safe_edit(
            cb.message,
            "Выбери категорию для удаления.\n"
            "<i>Записи с этой категорией удалены не будут.</i>",
            reply_markup=kb.cats_delete_kb(cats),
        )


# ---------- Pro ----------

@router.callback_query(F.data == "pro:info")
async def cb_pro_info(cb: CallbackQuery):
    if db.is_pro(cb.from_user.id):
        await cb.answer()
        return
    await safe_edit(
        cb.message,
        f"⭐ <b>Поддержать разработку</b>\n\n"
        f"Одноразовый платёж — <b>{PRO_STARS} звёзд Telegram</b>.",
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
        description=f"Одноразовый платёж — {PRO_STARS} звёзд Telegram",
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
        await msg.answer(
            "✅ Спасибо!",
            reply_markup=kb.main_menu(is_pro=True),
        )


# ---------- Fallback ----------

@router.message()
async def fallback(msg: Message):
    await msg.answer(
        "Нажми кнопку <b>➖ Расход</b> или <b>➕ Доход</b>, чтобы начать.",
        reply_markup=kb.main_menu(is_pro=db.is_pro(msg.from_user.id)),
    )
