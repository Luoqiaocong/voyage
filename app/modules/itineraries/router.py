from fastapi import APIRouter, Depends
from app.core.route import UnifiedRoute
from app.modules.itineraries.service import ItineraryService
from app.modules.itineraries.schemas import ItineraryExtractRequest
from starlette import status
from fastapi_utils.cbv import cbv



router = APIRouter(prefix="/itineraries", tags=["itineraries"], route_class=UnifiedRoute)

@cbv(router)
class ItineraryRouter:
    service :ItineraryService=Depends()


    @router.post("/extract", status_code=status.HTTP_200_OK, summary="【临时】提取结构化行程，不落库")
    async def extract_itinerary(self,
        req: ItineraryExtractRequest,
    ):
        return await self.service.extract_llm_output(req.conversation_id)