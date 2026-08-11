class ItineraryService:
    async def generate(self, destination: str, days: int, preferences: list[str]) -> str:
        # TODO: implement itinerary logic
        return f"Plan for {destination} ({days} days): ..."


itinerary_service = ItineraryService()