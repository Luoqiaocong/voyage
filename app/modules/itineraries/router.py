from fastapi import APIRouter
from app.modules.itineraries.service import itinerary_service
from app.modules.itineraries.schemas import ItineraryRequest, ItineraryResponse

router = APIRouter(prefix="/itineraries", tags=["itineraries"])


@router.post("/generate", response_model=ItineraryResponse)
async def generate_itinerary(req: ItineraryRequest):
    plan = await itinerary_service.generate(req.destination, req.days, req.preferences)
    return ItineraryResponse(plan=plan, destination=req.destination, days=req.days)