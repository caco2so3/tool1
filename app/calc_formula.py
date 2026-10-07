import math


def calc_ingredient_ml(needed: float, sum_per_portion: float, ingr_per_portion: float) -> float:
    """
    Формула:
        ОКРВНИЗ( (needed / sum_per_portion) * ingr_per_portion * 1000 ; 5 )

    - needed           — сколько ПФ нужно получить (в тех же единицах, что порция)
    - sum_per_portion  — сумма всех ингредиентов одной порции
    - ingr_per_portion — количество одного ингредиента на порцию
    Результат — в миллилитрах, округлён вниз до кратного 5.
    """
    if sum_per_portion <= 0:
        return 0.0
    raw = (needed / sum_per_portion) * ingr_per_portion * 1000.0
    return float(math.floor(raw / 5.0) * 5)


def calc_card(card: dict, needed: float) -> dict:
    """
    card = {'id', 'name', 'items': [{'product_id', 'product_name',
              'qty_per_portion', 'unit'}]}
    Возвращает раскладку по ингредиентам для нужного объёма.
    """
    items = card.get("items", [])
    sum_per_portion = sum(i["qty_per_portion"] for i in items)
    out_items = []
    for i in items:
        ml = calc_ingredient_ml(needed, sum_per_portion, i["qty_per_portion"])
        out_items.append({
            "product_id": i["product_id"],
            "product_name": i["product_name"],
            "unit": i.get("unit") or "мл",
            "qty_per_portion": i["qty_per_portion"],
            "result_ml": ml,
        })
    return {
        "card_id": card["id"],
        "name": card["name"],
        "needed": needed,
        "sum_per_portion": sum_per_portion,
        "items": out_items,
    }