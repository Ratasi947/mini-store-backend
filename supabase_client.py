import os
from supabase import create_client, Client

# SẾP CẦN THAY THẾ 2 DÒNG DƯỚI ĐÂY BẰNG THÔNG TIN THẬT CỦA SẾP
SUPABASE_URL = "https://czcxtrpgunuksiqvouhi.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6Y3h0cnBndW51a3NpcXZvdWhpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ2MTgxMTAsImV4cCI6MjA5MDE5NDExMH0.QwpHKwsdW7ZpDhkHsI3BVgxYnTeg4Tm_8zPl-GE3uCo"

# Khởi tạo kết nối
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)