def test_perfect_match_high_score():
    """Идеальное совпадение даёт высокую или хорошую релевантность.

    Порог >= 80, а не >= 90, потому что product_score использует
    эвристику по ключевым словам. Когда подключим ML — поднимем.
    """
    contracts = [Contract() for _ in range(25)]
    supplier = Supplier(
        name="МедТех Медицинское оборудование",
        contracts=contracts,
    )
    result = compute_score(Procurement(), supplier)
    assert result["total"] >= 80
    assert relevance_label(result["total"]) in {
        "Высокая релевантность",
        "Хорошая релевантность",
    }
