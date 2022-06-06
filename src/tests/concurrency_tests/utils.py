async def post(session, url, data, **kwargs):
    async with session.post(url, data=data, **kwargs) as response:
        return await response.text()
