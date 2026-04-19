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

# KHUÔN MẪU DỮ LIỆU NHÂN SỰ
class StaffCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str
    store_id: int
    dob: str = None
    hometown: str = None

class StaffUpdate(BaseModel):
    full_name: str
    role: str
    dob: str = None
    hometown: str = None

# HÀM GHI NHẬT KÝ NỘI BỘ
def log_action(store_id, action, target_name, performed_by_name, details):
    try:
        supabase.table("staff_logs").insert({
            "store_id": store_id, "action": action, 
            "target_name": target_name, "performed_by_name": performed_by_name, 
            "details": details
        }).execute()
    except Exception as e:
        print("Lỗi ghi log:", e)

# ==========================================
# API 4.1: TẠO TÀI KHOẢN (Đã thêm thông tin mới + Ghi log)
# ==========================================
@app.post("/api/create-staff")
def create_staff(new_staff: StaffCreate, user: dict = Depends(verify_token)):
    try:
        if str(user.get("role")) not in ["master", "owner"]: raise HTTPException(status_code=403, detail="Không có quyền!")
        target_store = user.get("store_id") if user.get("role") == "owner" else new_staff.store_id

        auth_response = supabase.auth.admin.create_user({"email": new_staff.email, "password": new_staff.password, "email_confirm": True})
        
        supabase.table("user_roles").insert({
            "id": auth_response.user.id, "store_id": target_store,
            "role": new_staff.role, "full_name": new_staff.full_name,
            "dob": new_staff.dob, "hometown": new_staff.hometown
        }).execute()

        log_action(target_store, "TẠO MỚI", new_staff.full_name, user.get("full_name"), f"Tạo tài khoản {new_staff.email} với chức vụ {new_staff.role}")
        return {"status": "ok", "message": "Thành công"}
    except Exception as e: return {"status": "error", "message": str(e)}

# ==========================================
# API 4.2: SỬA TÀI KHOẢN
# ==========================================
@app.put("/api/staff/{target_id}")
def update_staff(target_id: str, staff_data: StaffUpdate, user: dict = Depends(verify_token)):
    try:
        if str(user.get("role")) not in ["master", "owner"]: raise HTTPException(status_code=403, detail="Không có quyền!")
        
        # Cập nhật thông tin trong bảng user_roles
        supabase.table("user_roles").update({
            "full_name": staff_data.full_name, "role": staff_data.role,
            "dob": staff_data.dob, "hometown": staff_data.hometown
        }).eq("id", target_id).execute()

        target_store = user.get("store_id") if user.get("role") == "owner" else supabase.table("user_roles").select("store_id").eq("id", target_id).execute().data[0]['store_id']
        log_action(target_store, "CHỈNH SỬA", staff_data.full_name, user.get("full_name"), f"Cập nhật thông tin/chức vụ thành {staff_data.role}")
        return {"status": "ok", "message": "Cập nhật thành công"}
    except Exception as e: return {"status": "error", "message": str(e)}

# ==========================================
# API 4.3: XÓA TÀI KHOẢN (Đuổi việc)
# ==========================================
@app.delete("/api/staff/{target_id}")
def delete_staff(target_id: str, target_name: str, user: dict = Depends(verify_token)):
    try:
        if str(user.get("role")) not in ["master", "owner"]: raise HTTPException(status_code=403, detail="Không có quyền!")
        if target_id == user.get("id"): raise HTTPException(status_code=403, detail="Không thể tự xóa chính mình!")

        target_store = user.get("store_id") if user.get("role") == "owner" else supabase.table("user_roles").select("store_id").eq("id", target_id).execute().data[0]['store_id']
        
        # 1. Xóa thông tin quyền
        supabase.table("user_roles").delete().eq("id", target_id).execute()
        # 2. Tiêu hủy hoàn toàn thẻ từ trong hệ thống Auth
        supabase.auth.admin.delete_user(target_id)

        log_action(target_store, "XÓA (NGHỈ VIỆC)", target_name, user.get("full_name"), f"Đã xóa hoàn toàn tài khoản khỏi hệ thống")
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}

# ==========================================
# API 4.4: XEM NHẬT KÝ
# ==========================================
@app.get("/api/staff-logs")
def get_staff_logs(user: dict = Depends(verify_token)):
    try:
        query = supabase.table("staff_logs").select("*").order("created_at", desc=True)
        if str(user.get("role")) != "master": query = query.eq("store_id", user.get("store_id"))
        result = query.execute()
        return {"status": "ok", "data": result.data}
    except Exception as e: return {"status": "error", "message": str(e)}
