def format_money(amount: float) -> str:
    if amount == int(amount):
        return f"{int(amount):,}".replace(",", " ")
    return f"{amount:,.2f}".replace(",", " ")
