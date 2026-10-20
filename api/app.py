"""Merchant Console demo API: catalog, stock and discount previews."""
import os
import sqlite3
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB_PATH = Path(os.environ.get('MERCHANT_DB', str(Path(__file__).with_name('merchant.sqlite3'))))
app = FastAPI(title='Merchant Console API')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['*'], allow_headers=['*'])


def db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL CHECK(price>=0), stock INTEGER NOT NULL CHECK(stock>=0))')
        if not conn.execute('SELECT 1 FROM products LIMIT 1').fetchone():
            conn.executemany('INSERT INTO products(name,category,price,stock) VALUES(?,?,?,?)', [
                ('Canvas Tote', 'Accessories', 18.5, 22), ('Ceramic Mug', 'Home', 12.0, 8), ('Desk Lamp', 'Home', 44.0, 0)])


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    category: str = Field(min_length=2, max_length=50)
    price: float = Field(ge=0, le=1000000)
    stock: int = Field(ge=0, le=1000000)


class StockChange(BaseModel):
    stock: int = Field(ge=0, le=1000000)


class Discount(BaseModel):
    price: float = Field(ge=0)
    percent: float = Field(ge=0, le=100)


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/api/products')
def list_products(search: str = ''):
    with db() as conn:
        records = conn.execute('SELECT * FROM products WHERE LOWER(name) LIKE ? ORDER BY id DESC', (f'%{search.lower()}%',)).fetchall()
        return [dict(r) for r in records]


@app.get('/api/stats')
def stats():
    with db() as conn:
        row = conn.execute('SELECT COUNT(*) count, SUM(CASE WHEN stock = 0 THEN 1 ELSE 0 END) out_of_stock, COALESCE(SUM(stock*price),0) inventory_value FROM products').fetchone()
        return dict(row)


@app.post('/api/products', status_code=201)
def add_product(product: ProductCreate):
    with db() as conn:
        cur = conn.execute('INSERT INTO products(name,category,price,stock) VALUES (?,?,?,?)',
                           (product.name.strip(), product.category.strip(), product.price, product.stock))
        return {'id': cur.lastrowid, **product.model_dump()}


@app.patch('/api/products/{product_id}/stock')
def update_stock(product_id: int, change: StockChange):
    with db() as conn:
        result = conn.execute('UPDATE products SET stock=? WHERE id=?', (change.stock, product_id))
        if not result.rowcount:
            raise HTTPException(status_code=404, detail='Product not found')
        return {'id': product_id, 'stock': change.stock}


@app.delete('/api/products/{product_id}', status_code=204)
def delete_product(product_id: int):
    with db() as conn:
        result = conn.execute('DELETE FROM products WHERE id=?', (product_id,))
        if not result.rowcount:
            raise HTTPException(status_code=404, detail='Product not found')


@app.post('/api/discount-preview')
def preview_discount(value: Discount):
    return {'original': value.price, 'discount_percent': value.percent, 'final': round(value.price * (1 - value.percent / 100), 2)}


init_db()
