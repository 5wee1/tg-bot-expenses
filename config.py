import os
from dotenv import load_dotenv

load_dotenv(override=True)

BOT_TOKEN = os.environ["BOT_TOKEN"]
DB_PATH = "expenses.db"
CURRENCY = "₽"
PRO_STARS = 50
