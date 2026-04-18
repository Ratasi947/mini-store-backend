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

# KHUÔN MẪU DỮ LIỆU TẠO TÀI KHOẢN (Khai báo dưới class Order)
class StaffCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str
    store_id: int

# ==========================================
# 4. API: TẠO TÀI KHOẢN NHÂN VIÊN MỚI
# ==========================================
@app.post("/api/create-staff")
def create_staff(new_staff: StaffCreate, user: dict = Depends(verify_token)):
    try:
        # 1. Kiểm tra An Ninh: Chỉ Master hoặc Owner mới có quyền tạo lính
        current_role = str(user.get("role", "")).strip().lower()
        if current_role not in ["master", "owner"]:
            raise HTTPException(status_code=403, detail="Chỉ Quản lý hoặc Chủ tịch mới được tạo tài khoản!")
            
        # NẾU LÀ OWNER: Ép cứng chỉ được tạo nhân viên cho cửa hàng của mình (Phòng ngừa tự hack)
        target_store_id = new_staff.store_id
        if current_role == "owner":
            target_store_id = user.get("store_id")

        # 2. Ra lệnh cho Supabase tạo User Authentication (Sử dụng Service Role Key)
        auth_response = supabase.auth.admin.create_user({
            "email": new_staff.email,
            "password": new_staff.password,
            "email_confirm": True # Tự động xác nhận Email, không cần bắt lính check hộp thư
        })
        
        # 3. Lấy UID của lính mới vừa tạo
        new_user_id = auth_response.user.id
        
        # 4. Bơm chức vụ và phân trạm vào bảng user_roles
        supabase.table("user_roles").insert({
            "id": new_user_id,
            "store_id": target_store_id,
            "role": new_staff.role,
            "full_name": new_staff.full_name
        }).execute()

        return {"status": "ok", "message": "Tạo tài khoản thành công!"}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
