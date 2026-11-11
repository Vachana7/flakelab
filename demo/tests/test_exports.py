from shop.exports import export_catalog


def test_export_catalog():
    assert export_catalog() == "catalog.csv"
