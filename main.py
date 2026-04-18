from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from supabase_client import supabase

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# ==========================================
# TRẠM KIỂM SOÁT: KIỂM TRA THẺ TỪ (TOKEN)
# ==========================================
def verify_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Vui lòng đăng nhập!")
    
    token = authorization.split(" ")[1]
    try:
        # 1. Nhờ Supabase xác thực thẻ từ
        user_response = supabase.auth.get_user(token)
        user_id = user_response.user.id
        
        # 2. Tìm xem thẻ này thuộc Cửa hàng số mấy
        role_response = supabase.table("user_roles").select("*").eq("id", user_id).single().execute()
        if not role_response.data:
            raise HTTPException(status_code=403, detail="Tài khoản chưa được phân công vào Cửa hàng nào!")
            
        return {
            "user_id": user_id,
            "store_id": role_response.data["store_id"],
            "role": role_response.data["role"]
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="Thẻ từ không hợp lệ hoặc đã hết hạn!")

# 1. API: LẤY SẢN PHẨM (Đã gắn Trạm kiểm soát)
@app.get("/api/products")
def get_products(user: dict = Depends(verify_token)):
    try:
        # CHỈ LẤY HÀNG CỦA ĐÚNG CỬA HÀNG ĐÓ
        result = supabase.table("products").select("*").eq("store_id", user["store_id"]).execute()
        return {"status": "ok", "data": result.data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 2. API: LƯU HÓA ĐƠN
@app.post("/api/checkout")
def checkout(order: Order, user: dict = Depends(verify_token)):
    try:
        items_data = [item.model_dump() for item in order.items]
        result = supabase.table("orders").insert({
            "total_amount": order.total_amount,
            "cash_given": order.cash_given,
            "change_amount": order.change_amount,
            "items": items_data,
            "store_id": user["store_id"],      # Gắn mác thuộc Cửa hàng nào
            "created_by": user["user_id"]      # Gắn mác Nhân viên nào thu tiền
        }).execute()
        return {"status": "ok", "message": "Thành công"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 3. API: BÁO CÁO DOANH THU
@app.get("/api/reports")
def get_reports(user: dict = Depends(verify_token)):
    try:
        # CHỈ LẤY BÁO CÁO CỦA CỬA HÀNG ĐÓ
        result = supabase.table("orders").select("*").eq("store_id", user["store_id"]).execute()
        return {"status": "ok", "data": result.data}
    except Exception as e:
        return {"status": "error", "message": str(e)}