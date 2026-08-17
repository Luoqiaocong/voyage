class AuthService:
    async def login(self, username: str, password: str) -> tuple[str, int]:
        # TODO: implement auth logic
        return "fake-token", 1


auth_service = AuthService()