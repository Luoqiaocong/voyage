

from app.core.ai.llm import get_llm
from app.core.ai.structured import extract_itinerary_plan
from app.modules.conversation.gateway import ConversationGateway
from app.modules.itineraries.schemas import ItineraryPlan


class ItineraryService:
    def __init__(self,):
        pass
    
    async def extract_llm_output(self,conversation_id:str):
        conv_gateway = ConversationGateway()
        messages = await conv_gateway.get_messages(conversation_id)
        output_recommend_json = await extract_itinerary_plan(messages[-1].get("content"))
        return output_recommend_json
    