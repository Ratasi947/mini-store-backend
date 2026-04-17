from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from supabase_client import supabase

app = FastAPI()

# Mở cửa cho Vercel gọi vào
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Sau này có thể thay bằng link Vercel của Sếp cho bảo mật
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# KHUÔN MẪU DỮ LIỆU
class CartItem(BaseModel):
    barcode: str
    name: str
    qty: int
    price: int
    total: int

class Order(BaseModel):
    total_amount: int
    cash_given: int
    change_amount: int
    items: List[CartItem]

# 1. API: LẤY SẢN PHẨM
@app.get("/api/products")
def get_products():
    try:
        result = supabase.table("products").select("*").execute()
        return {"status": "ok", "data": result.data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 2. API: LƯU HÓA ĐƠN
@app.post("/api/checkout")
def checkout(order: Order):
    try:
        items_data = [item.model_dump() for item in order.items]
        result = supabase.table("orders").insert({
            "total_amount": order.total_amount,
            "cash_given": order.cash_given,
            "change_amount": order.change_amount,
            "items": items_data
        }).execute()
        return {"status": "ok", "message": "Thành công"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 3. API: BÁO CÁO DOANH THU
@app.get("/api/reports")
def get_reports():
    try:
        result = supabase.table("orders").select("*").execute()
        return {"status": "ok", "data": result.data}
    except Exception as e:
        return {"status": "error", "message": str(e)}