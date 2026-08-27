import os
import time
import uuid
from dotenv import load_dotenv
from locust import HttpUser, task, between
import json
load_dotenv()

password = os.environ["PASSWORD"]
class ChatUser(HttpUser):
    wait_time = between(2, 5)

    def on_start(self):
        # One stable session id per simulated user — mirrors a real user
        # keeping the same session for their whole visit.

        response = self.client.post("/api/auth/login", json={
            "email": "saharsh.vashishtha@gmail.com",
            "password": password
        })

        if response.status_code not in [201,200]:
            print(f"Login failed: {response.status_code} {response.text}")
            return

        access_token = response.json()["accessToken"]
        self.client.headers.update({"Authorization": f"Bearer {access_token}"})


        response2 = self.client.post("/api/session/create", json={
        })

        if(response2.status_code!=201):
            print(f"failed to create session: {response2.status_code} {response2.text}")
            return

        self.session_id=response2.json()["sessionId"]

    @task
    def send_chat_query(self):
        turn_id = str(uuid.uuid4())

        start_time = time.monotonic()
        first_token_time = None
        buffer = ""

        with self.client.post(
            "/api/query/stream",
            json={
                "query": "In one sentence, what year did the GDPR take effect??",
                "sessionId": self.session_id,
                "turnId": turn_id,
            },
            stream=True,
            catch_response=True,
        ) as response:
            for chunk in response.iter_content(chunk_size=None):
                if not chunk:
                    continue
                buffer += chunk.decode("utf-8", errors="replace")

                # Process every complete SSE message currently in the buffer
                while "\n\n" in buffer:
                    message, buffer = buffer.split("\n\n", 1)
                    if not message.startswith("data:"):
                        continue

                    payload = message[len("data:"):].strip()
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    if "token" in event and first_token_time is None:
                        first_token_time = time.monotonic()
                        ttft_ms = (first_token_time - start_time) * 1000

                        self.environment.events.request.fire(
                            request_type="POST",
                            name="/api/query/stream [TTFT-real-token]",
                            response_time=ttft_ms,
                            response_length=len(event["token"]),
                            exception=None,
                        )
            total_time = time.monotonic() - start_time
            self.environment.events.request.fire(
            request_type="POST",
            name="/api/query/stream [total-duration]",
            response_time=total_time * 1000,
            response_length=len(buffer),
            exception=None,
            )

            response.success()

