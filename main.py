from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from supabase_client import supabase
from datetime import datetime

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
# CẬP NHẬT API 2: THANH TOÁN (TỰ ĐỘNG TRỪ KHO)
# ==========================================
@app.post("/api/checkout")
def checkout(order: Order, user: dict = Depends(verify_token)):
    try:
        items_data = [item.model_dump() for item in order.items]
        store_to_save = user.get("store_id") if user.get("store_id") is not None else 1
            
        # Lưu hóa đơn
        supabase.table("orders").insert({
            "total_amount": order.total_amount, "cash_given": order.cash_given,
            "change_amount": order.change_amount, "items": items_data,
            "store_id": store_to_save, "created_by": user.get("id")
        }).execute()
        
        # 🚀 MA THUẬT TRỪ KHO TỰ ĐỘNG
        for item in order.items:
            prod_req = supabase.table("products").select("stock_qty").eq("barcode", item.barcode).execute()
            if prod_req.data:
                current_stock = prod_req.data[0].get("stock_qty", 0)
                new_stock = current_stock - item.qty
                supabase.table("products").update({"stock_qty": new_stock}).eq("barcode", item.barcode).execute()

        return {"status": "ok", "message": "Thành công"}
    except Exception as e: return {"status": "error", "message": str(e)}

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
    log_detail: str = None

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
# API 4.2: SỬA TÀI KHOẢN (Đã nhận Log chi tiết)
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
        
        # Ghi chính xác những gì Frontend báo cáo
        chi_tiet_log = staff_data.log_detail if staff_data.log_detail else "Cập nhật thông tin chung"
        
        log_action(target_store, "CHỈNH SỬA", staff_data.full_name, user.get("full_name"), chi_tiet_log)
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

# ==========================================
# API 5: LẤY LỊCH SỬ BÁN HÀNG (CÓ LỌC NGÀY/THÁNG)
# ==========================================
@app.get("/api/sales-history")
def get_sales_history(
    start_date: str = None, 
    end_date: str = None, 
    store_id: int = None, 
    user: dict = Depends(verify_token)
):
    try:
        query = supabase.table("orders").select("*").order("created_at", desc=True)
        
        # 1. Phân quyền lọc Trạm
        role = str(user.get("role", "")).strip().lower()
        if role != "master":
            # Nếu là lính/quản lý -> Chỉ được xem lịch sử trạm của mình
            safe_store_id = user.get("store_id") if user.get("store_id") is not None else 0
            query = query.eq("store_id", safe_store_id)
        else:
            # Nếu là Chủ tịch -> Lọc theo Trạm đang chọn trên màn hình
            if store_id is not None:
                query = query.eq("store_id", store_id)

        # 2. Lọc theo thời gian (Từ đầu ngày A đến cuối ngày B)
        if start_date:
            query = query.gte("created_at", f"{start_date}T00:00:00")
        if end_date:
            query = query.lte("created_at", f"{end_date}T23:59:59")
            
        result = query.execute()
        orders = result.data
        
        # 3. Dịch UID người bán thành Tên nhân viên
        users_req = supabase.table("user_roles").select("id, full_name").execute()
        user_map = {u["id"]: u["full_name"] for u in users_req.data} if users_req.data else {}
        
        for o in orders:
            o["seller_name"] = user_map.get(o.get("created_by"), "Không xác định")
            
        return {"status": "ok", "data": orders}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# KHUÔN MẪU DỮ LIỆU HÀNG HÓA
class ProductCreate(BaseModel):
    barcode: str
    name: str
    price: int
    category: str
    icon: str
    store_id: int
    stock_qty: int = 0
    import_price: int = 0
    safe_stock: int = 10
    supplier: str = ""
    
class StockImport(BaseModel):
    add_qty: int
    import_price: int
    supplier: str
# ==========================================
# CẬP NHẬT API 6.1: TẠO SẢN PHẨM MỚI (Lưu tồn kho)
# ==========================================
@app.post("/api/products")
def create_product(product: ProductCreate, user: dict = Depends(verify_token)):
    try:
        role = str(user.get("role", "")).strip().lower()
        if role not in ["master", "owner"]: raise HTTPException(status_code=403, detail="Chỉ Quản lý mới được nhập kho!")
        target_store = user.get("store_id") if role == "owner" else product.store_id
        
        supabase.table("products").insert({
            "barcode": product.barcode, "name": product.name, "price": product.price, 
            "category": product.category, "icon": product.icon, "store_id": target_store,
            "stock_qty": product.stock_qty, "import_price": product.import_price,
            "safe_stock": product.safe_stock, "supplier": product.supplier,
            "last_imported_by": user.get("full_name"),
            "last_imported_at": datetime.now().isoformat()
        }).execute()
        return {"status": "ok", "message": "Thêm sản phẩm thành công!"}
    except Exception as e: return {"status": "error", "message": str(e)}

# ==========================================
# API 6.2: XÓA SẢN PHẨM
# ==========================================
@app.delete("/api/products/{barcode}")
def delete_product(barcode: str, user: dict = Depends(verify_token)):
    try:
        role = str(user.get("role", "")).strip().lower()
        if role not in ["master", "owner"]: raise HTTPException(status_code=403, detail="Chỉ Quản lý mới được xóa hàng!")
        
        supabase.table("products").delete().eq("barcode", barcode).execute()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# API 6.3: NHẬP THÊM LÔ HÀNG (Sản phẩm đã có sẵn)
# ==========================================
@app.put("/api/products/{barcode}/import")
def import_stock(barcode: str, stock_data: StockImport, user: dict = Depends(verify_token)):
    try:
        if str(user.get("role")) not in ["master", "owner"]: raise HTTPException(status_code=403, detail="Cấp quyền quản lý để thực hiện!")
        
        prod_req = supabase.table("products").select("stock_qty").eq("barcode", barcode).execute()
        if not prod_req.data: raise HTTPException(status_code=404, detail="Không tìm thấy mã vạch này!")
        
        new_total_qty = prod_req.data[0].get("stock_qty", 0) + stock_data.add_qty
        
        supabase.table("products").update({
            "stock_qty": new_total_qty,
            "import_price": stock_data.import_price, # Cập nhật giá vốn mới nhất
            "supplier": stock_data.supplier,
            "last_imported_by": user.get("full_name"),
            "last_imported_at": datetime.now().isoformat()
        }).eq("barcode", barcode).execute()
        
        return {"status": "ok", "message": "Nhập kho thành công"}
    except Exception as e: return {"status": "error", "message": str(e)}
