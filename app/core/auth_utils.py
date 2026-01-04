from firebase_admin import auth

def get_uid_from_request(request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise Exception("Missing Authorization Bearer token")

    id_token = auth_header.split("Bearer ", 1)[1].strip()
    decoded = auth.verify_id_token(id_token)
    return decoded["uid"]
