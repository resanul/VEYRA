def test_catalog_view_module_exists() -> None:
    from veyra.providers.catalog_view import CatalogView
    assert CatalogView.__name__ == "CatalogView"
