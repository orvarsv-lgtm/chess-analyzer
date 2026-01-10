import os
from supabase import create_client, Client

_SUPABASE_URL = os.environ.get("SUPABASE_URL")
_SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not _SUPABASE_URL or not _SUPABASE_KEY:
    raise RuntimeError("Supabase URL and Service Role Key must be set in environment variables.")

supabase: Client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
