import os
import tempfile
from fastapi.testclient import TestClient
import app as module


def test_merchant_workflow():
    with tempfile.TemporaryDirectory() as temp:
        module.DB_PATH = __import__('pathlib').Path(temp) / 'db.sqlite3'
        module.init_db()
        client = TestClient(module.app)
        assert client.get('/health').json()['status'] == 'ok'
        assert len(client.get('/api/products').json()) == 3
        p = client.post('/api/products', json={'name': 'Test Hat', 'category': 'Clothing', 'price': 20, 'stock': 2})
        assert p.status_code == 201
        pid = p.json()['id']
        assert client.patch(f'/api/products/{pid}/stock', json={'stock': 0}).json()['stock'] == 0
        assert client.get('/api/stats').json()['out_of_stock'] == 2
        assert client.post('/api/discount-preview', json={'price': 50, 'percent': 20}).json()['final'] == 40
        assert client.post('/api/products', json={'name': 'X', 'category': 'C', 'price': -1, 'stock': 3}).status_code == 422
        assert client.delete(f'/api/products/{pid}').status_code == 204
        assert client.patch(f'/api/products/{pid}/stock', json={'stock': 4}).status_code == 404
