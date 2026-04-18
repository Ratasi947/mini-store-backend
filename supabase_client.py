import os
from supabase import create_client, Client

# SẾP CẦN THAY THẾ 2 DÒNG DƯỚI ĐÂY BẰNG THÔNG TIN THẬT CỦA SẾP
SUPABASE_URL = "https://czcxtrpgunuksiqvouhi.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6Y3h0cnBndW51a3NpcXZvdWhpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDYxODExMCwiZXhwIjoyMDkwMTk0MTEwfQ.nMgzrqYorrsVjm-d-S2Eo9BQkB3LKA7oYv1qULzUk90"

# Khởi tạo kết nối
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
