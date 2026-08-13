from uuid import UUID
import uuid
def get_id():
    return f"sess_{str(uuid.uuid4())}"