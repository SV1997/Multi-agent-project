# test_agent_stream.py (temporary)
import httpx
import asyncio
import json
import sys
import base64

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "http://localhost:3000/query/stream"
# HEADERS = {"x-internal-secret": "dev-secret-change-in-prod"}

QUERIES = {
    "legal": "are we compliant with GDPR right now?",
}

def decode_jwt_payload(token: str) -> dict:
    payload_b64 = token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))

async def stream_query(client: httpx.AsyncClient, domain: str, query: str):
    print(f"\n=== {domain} ===")
    print(f"query: {query}")
    login_response = await client.post(
            "http://localhost:3000/auth/login",
            json={
                "email": "test1@test.com",
                "password": "Password123",
            },
        )

    login_response.raise_for_status()

    access_token = login_response.json()["accessToken"]
    print("Got token")
    print("Payload:", decode_jwt_payload(access_token))
    tokens = []
    async with client.stream(
        "POST",
        BASE_URL,
        json={
            "query": query
            # "human_response": {
            #         "revised_answer": "what is GDPR ask for human review before answer",
            #         "approved": True,
            #         "edited": True
            #     },
            #     "thread_id":"dd23858c-8e80-4046-a761-ca68dfcc6615"
            },
        headers={
                "Authorization": f"Bearer {access_token}"
            },
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                print("\n--- stream complete ---")
                break

            event = json.loads(payload)
            if "token" in event:
                token = event["token"]
                tokens.append(token)
                safe_token = token.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
                    sys.stdout.encoding or "utf-8"
                )
                print(safe_token, end="", flush=True)
            elif event.get("status") == "paused_for_review":
                print("\n--- paused for human review ---")
                print(json.dumps(event["review_payload"], indent=2, default=str))
                print(f"thread_id: {event['thread_id']}")
                thread_id = event['thread_id']
            else:
                print(f"\n--- unexpected event ---\n{event}")
    # async with client.stream(
    #     "POST",
    #     BASE_URL+"/resume",
    #     json={
    #         # "query": query
    #         "human_response": {
    #                 "revised_answer": "what is GDPR ask for human review before answer",
    #                 "approved": True,
    #                 "edited": True
    #             },
    #             "thread_id":thread_id
    #         },
    #     headers={
    #             "Authorization": f"Bearer {access_token}"
    #         },
    # ) as response:
    #     response.raise_for_status()
    #     async for line in response.aiter_lines():
    #         if not line or not line.startswith("data:"):
    #             continue
    #         payload = line[len("data:"):].strip()
    #         if payload == "[DONE]":
    #             print("\n--- stream complete ---")
    #             break

    #         event = json.loads(payload)
    #         if "token" in event:
    #             token = event["token"]
    #             tokens.append(token)
    #             safe_token = token.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
    #                 sys.stdout.encoding or "utf-8"
    #             )
    #             print(safe_token, end="", flush=True)
    #         elif event.get("status") == "paused_for_review":
    #             print("\n--- paused for human review ---")
    #             print(json.dumps(event["review_payload"], indent=2, default=str))
    #             print(f"thread_id: {event['thread_id']}")
    #             thread_id = event['thread_id']
    #         else:
    #             print(f"\n--- unexpected event ---\n{event}")

    return "".join(tokens)


async def main():
    async with httpx.AsyncClient(timeout=60.0) as client:
        for domain, query in QUERIES.items():
            await stream_query(client, domain, query)
# "human_response": {
#                     "revised_answer": "what is GDPR ask for human review before answer",
#                     "approved": True,
#                     "edited": True
#                 },
#                 "thread_id":"5b7a88a7-f691-41f1-a7cc-a3768cef0480"

if __name__ == "__main__":
    asyncio.run(main())
