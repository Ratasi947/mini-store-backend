import os
from supabase import create_client, Client

# SẾP CẦN THAY THẾ 2 DÒNG DƯỚI ĐÂY BẰNG THÔNG TIN THẬT CỦA SẾP
SUPABASE_URL = "https://czcxtrpgunuksiqvouhi.supabase.co"
SUPABASE_KEY = "sb_secret_1vBCewUiNjHizvJ_pJk5dg_01NbPx47"

# Khởi tạo kết nối
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)