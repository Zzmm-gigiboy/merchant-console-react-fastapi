"""Comprehensive test suite for Merchant Console FastAPI backend."""
from pathlib import Path
import tempfile
import pytest
from fastapi.testclient import TestClient
import app as module


@pytest.fixture
def test_client():
    """Create an isolated test client with a fresh temporary SQLite database."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_file = Path(temp_dir) / "test_merchant.sqlite3"
        module.DB_PATH = db_file
        module.init_db()
        with TestClient(module.app) as client:
            yield client


def test_health_check(test_client):
    """Verify health probe returns status ok."""
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_initial_catalog_seeded(test_client):
    """Verify default seeded products are loaded upon database initialization."""
    response = test_client.get("/api/products")
    assert response.status_code == 200
    products = response.json()
    assert len(products) == 3
    names = {p["name"] for p in products}
    assert names == {"Canvas Tote", "Ceramic Mug", "Desk Lamp"}


def test_product_search_and_filtering(test_client):
    """Verify search filter by substring and case-insensitive matching."""
    # Search match
    res_tote = test_client.get("/api/products?search=canvas")
    assert res_tote.status_code == 200
    assert len(res_tote.json()) == 1
    assert res_tote.json()[0]["name"] == "Canvas Tote"

    # Case-insensitive partial match
    res_mug = test_client.get("/api/products?search=MUG")
    assert res_mug.status_code == 200
    assert len(res_mug.json()) == 1
    assert res_mug.json()[0]["name"] == "Ceramic Mug"

    # Non-matching query
    res_none = test_client.get("/api/products?search=NonExistent")
    assert res_none.status_code == 200
    assert len(res_none.json()) == 0


def test_create_product_success(test_client):
    """Verify creating a new merchant catalog item."""
    payload = {
        "name": "Mechanical Keyboard",
        "category": "Electronics",
        "price": 129.99,
        "stock": 15,
    }
    response = test_client.post("/api/products", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "Mechanical Keyboard"
    assert data["category"] == "Electronics"
    assert data["price"] == 129.99
    assert data["stock"] == 15

    # Verify presence in list
    all_products = test_client.get("/api/products").json()
    assert len(all_products) == 4
    assert any(p["name"] == "Mechanical Keyboard" for p in all_products)


@pytest.mark.parametrize(
    "invalid_payload,expected_error_field",
    [
        ({"name": "A", "category": "Office", "price": 10.0, "stock": 5}, "name"),
        ({"name": "Valid Name", "category": "Office", "price": -5.0, "stock": 5}, "price"),
        ({"name": "Valid Name", "category": "Office", "price": 10.0, "stock": -1}, "stock"),
        ({"name": "Valid Name", "category": "Office", "price": 1000001.0, "stock": 1}, "price"),
        ({"name": "Missing Fields"}, "category"),
    ],
)
def test_create_product_validation_failure(test_client, invalid_payload, expected_error_field):
    """Verify 422 Unprocessable Entity on schema validation violations."""
    response = test_client.post("/api/products", json=invalid_payload)
    assert response.status_code == 422
    details = response.json().get("detail", [])
    locs = [loc for err in details for loc in err.get("loc", [])]
    assert expected_error_field in locs


def test_update_stock_success(test_client):
    """Verify updating inventory stock for a product."""
    response = test_client.patch("/api/products/1/stock", json={"stock": 50})
    assert response.status_code == 200
    assert response.json() == {"id": 1, "stock": 50}

    # Verify change reflected in list
    products = test_client.get("/api/products").json()
    p1 = next(p for p in products if p["id"] == 1)
    assert p1["stock"] == 50


def test_update_stock_not_found(test_client):
    """Verify 404 response when updating non-existent product ID."""
    response = test_client.patch("/api/products/99999/stock", json={"stock": 10})
    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found"


def test_update_stock_invalid_payload(test_client):
    """Verify 422 response when updating stock with invalid data."""
    response = test_client.patch("/api/products/1/stock", json={"stock": -10})
    assert response.status_code == 422


def test_delete_product_workflow(test_client):
    """Verify deleting a product returns 204, and subsequent operations return 404."""
    del_res = test_client.delete("/api/products/1")
    assert del_res.status_code == 204

    # Subsequent deletion returns 404
    del_again = test_client.delete("/api/products/1")
    assert del_again.status_code == 404
    assert del_again.json()["detail"] == "Product not found"

    # Stock update on deleted product returns 404
    patch_del = test_client.patch("/api/products/1/stock", json={"stock": 5})
    assert patch_del.status_code == 404


def test_metrics_and_inventory_stats(test_client):
    """Verify aggregate stats: total product count, out-of-stock count, and total inventory value."""
    stats = test_client.get("/api/stats").json()
    assert stats["count"] == 3
    assert stats["out_of_stock"] == 1
    assert abs(stats["inventory_value"] - 503.0) < 0.01

    # Add another out-of-stock product
    test_client.post(
        "/api/products",
        json={"name": "Sold Out Poster", "category": "Art", "price": 15.0, "stock": 0},
    )
    new_stats = test_client.get("/api/stats").json()
    assert new_stats["count"] == 4
    assert new_stats["out_of_stock"] == 2
    assert abs(new_stats["inventory_value"] - 503.0) < 0.01

    # Restock Desk Lamp (ID 3)
    test_client.patch("/api/products/3/stock", json={"stock": 10})
    restocked_stats = test_client.get("/api/stats").json()
    assert restocked_stats["out_of_stock"] == 1
    # 503.0 + (10 * 44.0) = 943.0
    assert abs(restocked_stats["inventory_value"] - 943.0) < 0.01


def test_discount_preview_calculation(test_client):
    """Verify discount calculation endpoint handles valid prices and percentages."""
    res = test_client.post("/api/discount-preview", json={"price": 100.0, "percent": 25.0})
    assert res.status_code == 200
    assert res.json() == {"original": 100.0, "discount_percent": 25.0, "final": 75.0}

    # Zero discount
    res_zero = test_client.post("/api/discount-preview", json={"price": 49.99, "percent": 0.0})
    assert res_zero.status_code == 200
    assert res_zero.json()["final"] == 49.99

    # 100% discount
    res_free = test_client.post("/api/discount-preview", json={"price": 80.0, "percent": 100.0})
    assert res_free.status_code == 200
    assert res_free.json()["final"] == 0.0


@pytest.mark.parametrize(
    "invalid_discount",
    [
        {"price": -10.0, "percent": 20.0},
        {"price": 50.0, "percent": -5.0},
        {"price": 50.0, "percent": 105.0},
    ],
)
def test_discount_preview_validation_422(test_client, invalid_discount):
    """Verify 422 response on out-of-range discount parameters."""
    res = test_client.post("/api/discount-preview", json=invalid_discount)
    assert res.status_code == 422


def test_windows_ntfs_temp_cleanup_no_lock():
    """Explicitly verify successive temporary database creations and teardowns do not raise WinError 32."""
    for i in range(3):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / f"cycle_{i}.sqlite3"
            module.DB_PATH = db_path
            module.init_db()
            with TestClient(module.app) as client:
                client.post("/api/products", json={"name": f"Item {i}", "category": "Test", "price": 10.0, "stock": 1})
                client.get("/api/products")
                client.get("/api/stats")


def test_merchant_workflow():
    """End-to-end integration test of complete merchant workflow."""
    with tempfile.TemporaryDirectory() as temp:
        module.DB_PATH = Path(temp) / "db.sqlite3"
        module.init_db()
        with TestClient(module.app) as client:
            assert client.get("/health").json()["status"] == "ok"
            assert len(client.get("/api/products").json()) == 3
            p = client.post("/api/products", json={"name": "Test Hat", "category": "Clothing", "price": 20, "stock": 2})
            assert p.status_code == 201
            pid = p.json()["id"]
            assert client.patch(f"/api/products/{pid}/stock", json={"stock": 0}).json()["stock"] == 0
            assert client.get("/api/stats").json()["out_of_stock"] == 2
            assert client.post("/api/discount-preview", json={"price": 50, "percent": 20}).json()["final"] == 40
            assert client.post("/api/products", json={"name": "X", "category": "C", "price": -1, "stock": 3}).status_code == 422
            assert client.delete(f"/api/products/{pid}").status_code == 204
            assert client.patch(f"/api/products/{pid}/stock", json={"stock": 4}).status_code == 404
