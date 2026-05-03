from supabase import create_client, Client
from .config import settings

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

def get_user(telegram_id: int):
    response = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
    return response.data[0] if response.data else None

def create_or_update_user(telegram_id: int, **kwargs):
    user = get_user(telegram_id)
    if user:
        response = supabase.table("users").update(kwargs).eq("telegram_id", telegram_id).execute()
    else:
        data = {"telegram_id": telegram_id, **kwargs}
        response = supabase.table("users").insert(data).execute()
    return response.data[0] if response.data else None

def upload_cv(telegram_id: int, file_content: bytes, filename: str) -> str:
    path = f"{telegram_id}/{filename}"
    # Remove existing if any (optional)
    try:
        supabase.storage.from_(settings.SUPABASE_BUCKET).remove([path])
    except:
        pass
    
    supabase.storage.from_(settings.SUPABASE_BUCKET).upload(
        path=path,
        file=file_content,
        file_options={"content-type": "application/pdf"}
    )
    return supabase.storage.from_(settings.SUPABASE_BUCKET).get_public_url(path)
