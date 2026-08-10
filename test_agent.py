import asyncio
import base64
import json
import httpx


def decode_jwt_payload(token: str) -> dict:
    payload_b64 = token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Login
        login_response = await client.post(
            "http://localhost:3000/auth/login",
            json={
                "email": "test1@test.com",
                "password": "Password1234",
            },
        )
        
        try:
            login_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            print(login_response.json())
            return

        token = login_response.json()["accessToken"]
        print("Got token")
        print("Payload:", decode_jwt_payload(token))

        # Normal POST request
#         response = await client.post(
#             "http://localhost:3000/query",
#             json={
#                 "query":"what is status of my leaves"
#             },
#             headers={
#                 "Authorization": f"Bearer {token}"
#             },
#             timeout=None,  # Optional: disable timeout for this request
#         )

#         print("Status:", response.status_code)
#         print(response.text)
# #  "human_response": {
#                     "revised_answer": "what is GDPR ask for human review before answer",
#                     "approved": True,
#                     "edited": True
#                 },
#                 "thread_id":"dfa1f8d9-103e-4092-af10-dcd2d3336079"

if __name__ == "__main__":
    asyncio.run(main())