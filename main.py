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
    incoming_qty: int = 0
    is_sale: bool = False
    
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
        if str(user.get("role")) not in ["master", "owner"]: raise HTTPException(status_code=403)
        target = user.get("store_id") if user.get("role") == "owner" else product.store_id
        supabase.table("products").insert({
            "barcode": product.barcode, "name": product.name, "price": product.price, 
            "category": product.category, "icon": product.icon, "store_id": target,
            "stock_qty": product.stock_qty, "import_price": product.import_price,
            "safe_stock": product.safe_stock, "supplier": product.supplier,
            "incoming_qty": product.incoming_qty, "is_sale": product.is_sale, # <--- Lưu Sale
            "last_imported_by": user.get("full_name"), "last_imported_at": datetime.now().isoformat()
        }).execute()
        return {"status": "ok"}
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
        if str(user.get("role")) not in ["master", "owner"]: raise HTTPException(status_code=403)
        
        prod_req = supabase.table("products").select("stock_qty, incoming_qty").eq("barcode", barcode).execute()
        if not prod_req.data: raise HTTPException(status_code=404)
        
        current_data = prod_req.data[0]
        new_total_qty = current_data.get("stock_qty", 0) + stock_data.add_qty
        
        # Hàng đã về thì trừ ở cột "Đang đặt" đi (không để âm)
        new_incoming = max(0, current_data.get("incoming_qty", 0) - stock_data.add_qty)
        
        supabase.table("products").update({
            "stock_qty": new_total_qty,
            "incoming_qty": new_incoming,
            "import_price": stock_data.import_price, 
            "supplier": stock_data.supplier,
            "last_imported_by": user.get("full_name"),
            "last_imported_at": datetime.now().isoformat()
        }).eq("barcode", barcode).execute()
        
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}

# ==========================================
# KHUÔN MẪU DỮ LIỆU NHÀ CUNG CẤP
# ==========================================
class SupplierCreate(BaseModel):
    name: str
    representative: str = ""
    phone_landline: str = ""
    phone_mobile: str = ""
    fax: str = ""
    address: str = "" 
    store_id: int

# ==========================================
# API 6.4: CẬP NHẬT (SỬA) SẢN PHẨM HIỆN TẠI
# ==========================================
@app.put("/api/products/{barcode}")
def update_product(barcode: str, product: ProductCreate, user: dict = Depends(verify_token)):
    try:
        if str(user.get("role")) not in ["master", "owner"]: raise HTTPException(status_code=403)
        supabase.table("products").update({
            "name": product.name, "price": product.price, "category": product.category, 
            "icon": product.icon, "stock_qty": product.stock_qty, "is_sale": product.is_sale, # <--- Cập nhật Sale
            "import_price": product.import_price, "safe_stock": product.safe_stock, 
            "supplier": product.supplier, "incoming_qty": product.incoming_qty
        }).eq("barcode", barcode).execute()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}

# ==========================================
# API 7: QUẢN LÝ NHÀ CUNG CẤP
# ==========================================
@app.get("/api/suppliers")
def get_suppliers(store_id: int, user: dict = Depends(verify_token)):
    try:
        # Lấy NCC của trạm hiện tại (hoặc có thể share chung nếu muốn)
        result = supabase.table("suppliers").select("*").eq("store_id", store_id).execute()
        return {"status": "ok", "data": result.data}
    except Exception as e: return {"status": "error", "message": str(e)}

@app.post("/api/suppliers")
def create_supplier(supplier: SupplierCreate, user: dict = Depends(verify_token)):
    try:
        if str(user.get("role")) not in ["master", "owner"]: raise HTTPException(status_code=403)
        supabase.table("suppliers").insert(supplier.model_dump()).execute()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}

# ==========================================
# KHUÔN MẪU DỮ LIỆU ĐẶT HÀNG & NHẬP KHO
# ==========================================
class POCreate(BaseModel):
    store_id: int
    supplier: str
    items: list
    expected_date: str = None

class POReceiveItem(BaseModel):
    barcode: str
    receive_qty: int
    import_price: int

class POReceive(BaseModel):
    po_id: int = None
    supplier: str
    items: list[POReceiveItem]

# ==========================================
# API 8.1: TẠO ĐƠN ĐẶT HÀNG (PO) + SINH MÃ PO TỰ ĐỘNG
# ==========================================
@app.post("/api/purchase-orders")
def create_po(po: POCreate, user: dict = Depends(verify_token)):
    try:
        # 1. TẠO MÃ ĐƠN HÀNG CHUẨN ERP (VD: 120260420001)
        today = datetime.now()
        date_str = today.strftime("%Y%m%d")
        start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        
        # Đếm số lượng đơn trong ngày của Trạm này
        records = supabase.table("purchase_orders").select("id").eq("store_id", po.store_id).gte("created_at", start_of_day).execute()
        daily_seq = len(records.data) + 1
        
        custom_po_id = f"{po.store_id}{date_str}{daily_seq:03d}" # Định dạng: [Trạm][YYYYMMDD][00X]

        # 2. LƯU ĐƠN ĐẶT KÈM MÃ VỪA TẠO
        res = supabase.table("purchase_orders").insert({
            "store_id": po.store_id, "supplier": po.supplier,
            "items": po.items, "expected_date": po.expected_date,
            "created_by_name": user.get("full_name"), "status": "PENDING",
            "purchase_orders_id": custom_po_id # <--- LƯU VÀO DB
        }).execute()
        new_po_id = res.data[0]['id']

        # 3. Cập nhật Hàng Đang Về vào SP
        for item in po.items:
            prod_req = supabase.table("products").select("incoming_qty").eq("barcode", item.get("barcode")).execute()
            if prod_req.data:
                curr_inc = prod_req.data[0].get("incoming_qty") or 0
                supabase.table("products").update({
                    "incoming_qty": curr_inc + item.get("order_qty"),
                    "incoming_date": po.expected_date
                }).eq("barcode", item.get("barcode")).execute()

        return {"status": "ok", "po_id": new_po_id, "custom_po_id": custom_po_id}
    except Exception as e: return {"status": "error", "message": str(e)}

@app.get("/api/purchase-orders")
def get_po(store_id: int, user: dict = Depends(verify_token)):
    try:
        res = supabase.table("purchase_orders").select("*").eq("store_id", store_id).order("created_at", desc=True).execute()
        return {"status": "ok", "data": res.data}
    except Exception as e: return {"status": "error", "message": str(e)}

# ==========================================
# API 8.2: NHẬP KHO LÔ HÀNG VỀ (GOODS RECEIPT)
# Tự động đối soát PO, Trừ hàng đang về, Cộng tồn kho
# ==========================================
@app.post("/api/receive-goods")
def receive_goods(gr: POReceive, user: dict = Depends(verify_token)):
    try:
        store_to_save = user.get("store_id") if user.get("role") != "master" else 1 # Lấy trạm hiện tại
        
        items_log = []
        for item in gr.items:
            # 1. Cập nhật tồn kho từng sản phẩm
            prod_req = supabase.table("products").select("stock_qty, incoming_qty, name").eq("barcode", item.barcode).execute()
            if prod_req.data:
                p_data = prod_req.data[0]
                new_stock = p_data.get("stock_qty", 0) + item.receive_qty
                # Nếu nhập từ PO, tự động trừ đi số lượng "Đang chờ về", không để âm
                new_incoming = max(0, p_data.get("incoming_qty", 0) - item.receive_qty) if gr.po_id else p_data.get("incoming_qty", 0)
                
                # Nếu hàng đã về hết, xóa ngày dự kiến
                new_inc_date = None if new_incoming == 0 else supabase.table("products").select("incoming_date").eq("barcode", item.barcode).execute().data[0].get("incoming_date")

                supabase.table("products").update({
                    "stock_qty": new_stock, "incoming_qty": new_incoming, "incoming_date": new_inc_date,
                    "import_price": item.import_price, "supplier": gr.supplier,
                    "last_imported_by": user.get("full_name"), "last_imported_at": datetime.now().isoformat()
                }).eq("barcode", item.barcode).execute()
                
                items_log.append({"barcode": item.barcode, "name": p_data.get("name"), "receive_qty": item.receive_qty, "import_price": item.import_price})

        # 2. Cập nhật trạng thái Đơn Đặt Hàng (nếu có mã PO)
        if gr.po_id:
            po_req = supabase.table("purchase_orders").select("items").eq("id", gr.po_id).execute()
            if po_req.data:
                po_items = po_req.data[0].get("items")
                all_completed = True
                
                # Đối soát số lượng: Cộng dồn số đã nhận vào JSON của PO
                for po_item in po_items:
                    for r_item in gr.items:
                        if po_item.get("barcode") == r_item.barcode:
                            po_item["received_qty"] = po_item.get("received_qty", 0) + r_item.receive_qty
                    
                    if po_item.get("received_qty", 0) < po_item.get("order_qty", 0):
                        all_completed = False # Còn món giao thiếu
                
                new_status = "COMPLETED" if all_completed else "PARTIAL"
                supabase.table("purchase_orders").update({"items": po_items, "status": new_status}).eq("id", gr.po_id).execute()

        # 3. Ghi vào Sổ Nhập Kho (Goods Receipt)
        supabase.table("goods_receipts").insert({
            "po_id": gr.po_id, "store_id": store_to_save, "supplier": gr.supplier,
            "items": items_log, "received_by_name": user.get("full_name")
        }).execute()

        return {"status": "ok", "message": "Nhập kho & Đối soát thành công!"}
    except Exception as e: return {"status": "error", "message": str(e)}

@app.get("/api/goods-receipts")
def get_goods_receipts(store_id: int, user: dict = Depends(verify_token)):
    try:
        res = supabase.table("goods_receipts").select("*").eq("store_id", store_id).order("created_at", desc=True).execute()
        return {"status": "ok", "data": res.data}
    except Exception as e: return {"status": "error", "message": str(e)}

# ==========================================
# API 8.3: HỦY ĐƠN ĐẶT HÀNG (TRẢ LẠI TRẠNG THÁI CHƯA ĐẶT)
# ==========================================
@app.put("/api/purchase-orders/{po_id}/cancel")
def cancel_po(po_id: int, user: dict = Depends(verify_token)):
    try:
        if str(user.get("role")) not in ["master", "owner"]: raise HTTPException(status_code=403)
        
        po_req = supabase.table("purchase_orders").select("*").eq("id", po_id).execute()
        if not po_req.data: raise HTTPException(status_code=404)
        po = po_req.data[0]
        
        if po["status"] in ["COMPLETED", "CANCELLED"]: 
            raise HTTPException(status_code=400, detail="Không thể hủy đơn đã hoàn thành hoặc đã bị hủy!")
        
        # 🚀 THÔNG MINH: Trừ lại số lượng Hàng Đang Về trong Kho
        for item in po["items"]:
            pending_qty = item.get("order_qty", 0) - item.get("received_qty", 0)
            if pending_qty > 0:
                p_req = supabase.table("products").select("incoming_qty").eq("barcode", item["barcode"]).execute()
                if p_req.data:
                    new_incoming = max(0, p_req.data[0].get("incoming_qty", 0) - pending_qty)
                    supabase.table("products").update({"incoming_qty": new_incoming}).eq("barcode", item["barcode"]).execute()
        
        # Đổi trạng thái PO thành Hủy
        supabase.table("purchase_orders").update({"status": "CANCELLED"}).eq("id", po_id).execute()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}
