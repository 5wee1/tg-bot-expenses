import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db, get_due_recurring, add_transaction, mark_recurring_triggered
from handlers import router
import keyboards as kb
from utils import format_money
from config import CURRENCY


async def recurring_checker(bot: Bot):
    while True:
        await asyncio.sleep(3600)
        try:
            due = get_due_recurring()
            for item in due:
                try:
                    sign = "➖" if item["type"] == "expense" else "➕"
                    name = item["comment"] or item["cat_name"]
                    await bot.send_message(
                        item["user_id"],
                        f"🔁 Напоминание\n\n"
                        f"{item['emoji']} <b>{item['cat_name']}</b> — {name}\n"
                        f"<b>{sign} {format_money(item['amount'])} {CURRENCY}</b>",
                        reply_markup=kb.recur_reminder_kb(item["id"]),
                    )
                    mark_recurring_triggered(item["id"])
                except Exception:
                    pass
        except Exception:
            pass


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(recurring_checker(bot))
    logging.info("Bot started. Press Ctrl+C to stop.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")
