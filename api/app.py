"""Merchant Console demo API: catalog, stock and discount previews."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB_PATH = Path(os.environ.get('MERCHANT_DB', str(Path(__file__).with_name('merchant.sqlite3'))))
app = FastAPI(title='Merchant Console API')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['*'], allow_headers=['*'])


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def escape_like(query: str) -> str:
    """Escape SQL LIKE special wildcard characters %, _, and backslash."""
    return query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


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
def list_products(search: str = '', category: str = ''):
    with db() as conn:
        sql = 'SELECT * FROM products WHERE 1=1'
        params = []
        if search:
            escaped = escape_like(search.strip().lower())
            sql += " AND LOWER(name) LIKE ? ESCAPE '\\'"
            params.append(f'%{escaped}%')
        if category:
            sql += ' AND LOWER(category) = ?'
            params.append(category.strip().lower())
        sql += ' ORDER BY id DESC'
        records = conn.execute(sql, params).fetchall()
        return [dict(r) for r in records]


@app.get('/api/stats')
def stats():
    with db() as conn:
        row = conn.execute('SELECT COUNT(*) count, SUM(CASE WHEN stock = 0 THEN 1 ELSE 0 END) out_of_stock, COALESCE(SUM(stock*price),0) inventory_value FROM products').fetchone()
        return dict(row)


@app.post('/api/products', status_code=201)
def add_product(product: ProductCreate):
    clean_name = product.name.strip()
    clean_category = product.category.strip()
    if len(clean_name) < 2:
        raise HTTPException(status_code=422, detail='Product name must be at least 2 non-whitespace characters')
    if len(clean_category) < 2:
        raise HTTPException(status_code=422, detail='Category must be at least 2 non-whitespace characters')
    with db() as conn:
        cur = conn.execute('INSERT INTO products(name,category,price,stock) VALUES (?,?,?,?)',
                           (clean_name, clean_category, product.price, product.stock))
        return {'id': cur.lastrowid, **product.model_dump(), 'name': clean_name, 'category': clean_category}


@app.patch('/api/products/{product_id}/stock')
def update_stock(product_id: int, change: StockChange):
    if product_id <= 0:
        raise HTTPException(status_code=422, detail='Product ID must be a positive integer')
    with db() as conn:
        result = conn.execute('UPDATE products SET stock=? WHERE id=?', (change.stock, product_id))
        if not result.rowcount:
            raise HTTPException(status_code=404, detail='Product not found')
        return {'id': product_id, 'stock': change.stock}


@app.delete('/api/products/{product_id}', status_code=204)
def delete_product(product_id: int):
    if product_id <= 0:
        raise HTTPException(status_code=422, detail='Product ID must be a positive integer')
    with db() as conn:
        result = conn.execute('DELETE FROM products WHERE id=?', (product_id,))
        if not result.rowcount:
            raise HTTPException(status_code=404, detail='Product not found')


@app.post('/api/discount-preview')
def preview_discount(value: Discount):
    savings = round(value.price * (value.percent / 100), 2)
    final = round(value.price - savings, 2)
    return {
        'original': value.price,
        'discount_percent': value.percent,
        'savings': savings,
        'final': max(0.0, final)
    }


init_db()
