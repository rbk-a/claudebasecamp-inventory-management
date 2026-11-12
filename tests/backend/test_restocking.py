"""
Tests for restocking API endpoints (demand forecast pricing and restock orders).
"""
from datetime import date, timedelta

import pytest

import main


@pytest.fixture(autouse=True)
def clear_restock_orders():
    """Reset the in-memory restock order store around each test."""
    main.restock_orders.clear()
    yield
    main.restock_orders.clear()


def _forecasts_by_sku(client):
    return {f["item_sku"]: f for f in client.get("/api/demand").json()}


class TestDemandForecastPricing:
    """Test that demand forecasts carry the fields restocking relies on."""

    def test_demand_forecast_cost_and_lead_time_types(self, client):
        """Test that every forecast has a positive unit cost and lead time."""
        response = client.get("/api/demand")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0
        for forecast in data:
            assert isinstance(forecast["unit_cost"], (int, float))
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["unit_cost"] > 0
            assert forecast["lead_time_days"] > 0


class TestRestockOrderEndpoints:
    """Test suite for restock order endpoints."""

    def test_get_all_restock_orders_empty(self, client):
        """Test that no restock orders exist initially."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restock_order(self, client):
        """Test submitting a valid restock order."""
        forecasts = _forecasts_by_sku(client)
        payload = {
            "items": [
                {"item_sku": "WDG-001", "quantity": 10},
                {"item_sku": "GSK-203", "quantity": 20},
            ],
            "budget": 10000,
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"] == "RST-0001"
        assert order["status"] == "Submitted"
        assert order["budget"] == 10000
        assert len(order["items"]) == 2

        for item in order["items"]:
            forecast = forecasts[item["item_sku"]]
            assert item["item_name"] == forecast["item_name"]
            assert item["unit_cost"] == forecast["unit_cost"]
            assert item["lead_time_days"] == forecast["lead_time_days"]
            assert abs(item["line_total"] - item["quantity"] * item["unit_cost"]) < 0.01

    def test_restock_order_total_calculation(self, client):
        """Test that the order total is the sum of the line totals."""
        payload = {
            "items": [
                {"item_sku": "MTR-304", "quantity": 2},
                {"item_sku": "FLT-405", "quantity": 15},
            ],
            "budget": 5000,
        }
        order = client.post("/api/restock-orders", json=payload).json()
        expected = sum(item["line_total"] for item in order["items"])
        assert abs(order["total_cost"] - expected) < 0.01

    def test_restock_order_lead_time_calculation(self, client):
        """Test that the order lead time is the longest line lead time and drives expected delivery."""
        forecasts = _forecasts_by_sku(client)
        skus = ["WDG-001", "MTR-304", "GSK-203"]
        payload = {
            "items": [{"item_sku": sku, "quantity": 1} for sku in skus],
            "budget": 10000,
        }
        order = client.post("/api/restock-orders", json=payload).json()

        expected_lead = max(forecasts[sku]["lead_time_days"] for sku in skus)
        assert order["lead_time_days"] == expected_lead

        submitted = date.fromisoformat(order["submitted_date"])
        expected_delivery = date.fromisoformat(order["expected_delivery"])
        assert submitted == date.today()
        assert expected_delivery - submitted == timedelta(days=expected_lead)

    def test_restock_order_ignores_client_prices(self, client):
        """Test that prices sent by the client are not trusted."""
        forecasts = _forecasts_by_sku(client)
        payload = {
            "items": [{"item_sku": "CTL-330", "quantity": 1, "unit_cost": 0.01}],
            "budget": 1000,
        }
        order = client.post("/api/restock-orders", json=payload).json()
        assert order["items"][0]["unit_cost"] == forecasts["CTL-330"]["unit_cost"]

    def test_submitted_restock_orders_listed_newest_first(self, client):
        """Test that submitted orders appear in GET, newest first."""
        for sku in ["WDG-001", "BRG-102"]:
            response = client.post(
                "/api/restock-orders",
                json={"items": [{"item_sku": sku, "quantity": 1}], "budget": 1000},
            )
            assert response.status_code == 201

        data = client.get("/api/restock-orders").json()
        assert [o["order_number"] for o in data] == ["RST-0002", "RST-0001"]

    def test_restock_orders_do_not_affect_customer_orders(self, client):
        """Test that restock orders are kept separate from customer orders."""
        before = len(client.get("/api/orders").json())
        client.post(
            "/api/restock-orders",
            json={"items": [{"item_sku": "WDG-001", "quantity": 1}], "budget": 1000},
        )
        assert len(client.get("/api/orders").json()) == before

    def test_restock_order_over_budget(self, client):
        """Test that an order exceeding the budget is rejected and not stored."""
        payload = {"items": [{"item_sku": "MTR-304", "quantity": 10}], "budget": 100}
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 400
        assert "exceeds budget" in response.json()["detail"].lower()
        assert client.get("/api/restock-orders").json() == []

    def test_restock_order_unknown_sku(self, client):
        """Test that an unknown SKU is rejected."""
        payload = {"items": [{"item_sku": "NOPE-999", "quantity": 1}], "budget": 1000}
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 400
        assert "unknown sku" in response.json()["detail"].lower()

    def test_restock_order_duplicate_sku(self, client):
        """Test that the same SKU twice in one order is rejected."""
        payload = {
            "items": [
                {"item_sku": "WDG-001", "quantity": 1},
                {"item_sku": "WDG-001", "quantity": 2},
            ],
            "budget": 1000,
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "payload",
        [
            {"items": [], "budget": 1000},
            {"items": [{"item_sku": "WDG-001", "quantity": 0}], "budget": 1000},
            {"items": [{"item_sku": "WDG-001", "quantity": -5}], "budget": 1000},
            {"items": [{"item_sku": "WDG-001", "quantity": 1}], "budget": -1},
            {"items": [{"item_sku": "WDG-001", "quantity": 1}]},
        ],
    )
    def test_restock_order_validation_errors(self, client, payload):
        """Test that invalid payloads return 422."""
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 422
