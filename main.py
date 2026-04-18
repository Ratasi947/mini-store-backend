from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from supabase_client import supabase

app = FastAPI()

# Mở cửa cho Vercel gọi vào
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# KHUÔN MẪU DỮ LIỆU
class CartItem(BaseModel):
    barcode: str
    name: str
    price: int
    qty: int
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
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token không hợp lệ!")
            
        user_id = user_response.user.id
        
        role_response = supabase.table("user_roles").select("*").eq("id", user_id).execute()
        if not role_response.data:
            raise HTTPException(status_code=403, detail="Tài khoản chưa được phân công!")
            
        return role_response.data[0] 
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Lỗi xác thực: {str(e)}")

# ==========================================
# 1. API: LẤY SẢN PHẨM (ĐÃ BỌC THÉP CHỐNG LỖI NONE)
# ==========================================
@app.get("/api/products")
def get_products(user: dict = Depends(verify_token)):
    try:
        query = supabase.table("products").select("*")
        
        # Xử lý dứt điểm vụ chữ hoa, chữ thường, dư khoảng trắng
        role = str(user.get("role", "")).strip().lower()
        store_id = user.get("store_id")
        
        if role != "master":
            # Nếu là nhân viên nhưng store_id bị NULL (None), thì ép nó về số 0 để không bị lỗi chữ "None"
            safe_store_id = store_id if store_id is not None else 0
            query = query.eq("store_id", safe_store_id)
            
        result = query.execute()
        return {"status": "ok", "data": result.data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# 2. API: LƯU HÓA ĐƠN
# ==========================================
@app.post("/api/checkout")
def checkout(order: Order, user: dict = Depends(verify_token)):
    try:
        items_data = [item.model_dump() for item in order.items]
        
        store_to_save = user.get("store_id")
        # Chủ tịch bán hàng hoặc người chưa có mã thì lưu tạm vào kho 1
        if store_to_save is None:
            store_to_save = 1
            
        result = supabase.table("orders").insert({
            "total_amount": order.total_amount,
            "cash_given": order.cash_given,
            "change_amount": order.change_amount,
            "items": items_data,
            "store_id": store_to_save,
            "created_by": user.get("id")
        }).execute()
        return {"status": "ok", "message": "Thành công"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# 3. API: BÁO CÁO DOANH THU
# ==========================================
@app.get("/api/reports")
def get_reports(user: dict = Depends(verify_token)):
    try:
        query = supabase.table("orders").select("*")
        
        role = str(user.get("role", "")).strip().lower()
        store_id = user.get("store_id")
        
        if role != "master":
            safe_store_id = store_id if store_id is not None else 0
            query = query.eq("store_id", safe_store_id)
            
        result = query.execute()
        return {"status": "ok", "data": result.data}
    except Exception as e:
        return {"status": "error", "message": str(e)}
