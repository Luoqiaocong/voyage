from pydantic import BaseModel


class ItineraryRequest(BaseModel):
    destination: str
    days: int = 3
    preferences: list[str] = []


class ItineraryResponse(BaseModel):
    plan: str
    destination: str
    days: int