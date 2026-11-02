"""Load test for the chat stream. Each virtual user logs in, keeps one session, and sends a weighted mix of
questions through POST /query/stream, reading the SSE stream to the end.

A request counts as SUCCESS only when the stream ended with the final answer ([DONE] after at least one token).
It is a FAILURE, with the reason as the exception text, when a typed error event arrived, the orchestrator's
technical-error answer came back, the stream ended with no answer, the HTTP status was not 2xx, or no bytes
arrived for 60s (stalled). Two extra metrics are recorded per request: time-to-first-token and total duration.

Environment:
    LOAD_EMAIL, PASSWORD   gateway login (required)
    LOCUST_HOST            base URL, default http://localhost:3000 (the gateway port)
    ALLOW_REMOTE=yes       required before a non-localhost host is allowed
"""
import json
import os
import random
import time
import uuid

from locust import HttpUser, between, events, task

HOST = os.environ.get("LOCUST_HOST", "http://localhost:3000")
EMAIL = os.environ.get("LOAD_EMAIL", "")
PASSWORD = os.environ.get("PASSWORD", "")
READ_TIMEOUT = 60                      # "no event within 60s" => stalled

QUESTIONS = [
    "How many casual leaves do I get?",
    "Tell me about leave",
    "Is PF deducted from my salary?",
    "What are the penalties under GDPR?",
    "How do I reset my VPN password?",
    "How do I claim travel expenses?",
]
TECH_ERROR = "i ran into a technical issue"      # the orchestrator's fixed error answer (routes.py TEMPLATE_ERROR_ANSWER)


@events.test_start.add_listener
def _guard(environment, **_):
    """Print the host and refuse a non-local host unless ALLOW_REMOTE=yes, so a load test cannot hit production."""
    local = any(h in HOST for h in ("localhost", "127.0.0.1"))
    print(f"LOAD TEST host = {HOST}")
    if not local and os.environ.get("ALLOW_REMOTE") != "yes":
        print(f"REFUSING: {HOST} is not localhost. Set ALLOW_REMOTE=yes to allow it.")
        environment.runner.quit()


def failure_reason(text, error_event):
    """The one-word reason a streamed request failed, or None if it carried a real answer."""
    low = text.lower()
    if "rate limit" in low or "429" in low or "too many requests" in low:
        return "groq_rate_limit"
    if error_event:
        return "error_event"
    if TECH_ERROR in low:
        return "orchestrator_error"
    if "couldn't understand this request well enough to route it" in low:    # the classifier failed (e.g. a Groq 429)
        return "classifier_failed"
    return None


class ChatUser(HttpUser):
    host = HOST
    wait_time = between(2, 5)

    def on_start(self):
        # One stable session per simulated user, as a real user keeps one session for their visit.
        r = self.client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, name="/auth/login")
        if r.status_code not in (200, 201):
            print(f"Login failed: {r.status_code} {r.text[:200]}")
            self.session_id = None
            return
        self.client.headers.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
        s = self.client.post("/session/create", json={}, name="/session/create")
        self.session_id = s.json()["sessionId"] if s.status_code in (200, 201) else None

    @task
    def send_chat_query(self):
        if not self.session_id:
            return
        start = time.monotonic()
        first_token = None
        answer, buffer, error_event, done = "", "", False, False
        try:
            with self.client.post(
                "/query/stream",
                json={"query": random.choice(QUESTIONS), "sessionId": self.session_id, "turnId": str(uuid.uuid4())},
                stream=True, catch_response=True, timeout=(10, READ_TIMEOUT), name="/query/stream",
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    response.failure(f"http_{response.status_code}")
                    return
                for chunk in response.iter_content(chunk_size=None):
                    if not chunk:
                        continue
                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\n\n" in buffer:                       # one complete SSE frame per blank-line boundary
                        message, buffer = buffer.split("\n\n", 1)
                        if not message.startswith("data:"):
                            continue
                        payload = message[len("data:"):].strip()
                        if payload == "[DONE]":
                            done = True
                            continue
                        try:
                            event = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        if event.get("type") == "error":
                            error_event = True
                        if "token" in event:
                            answer += event["token"]
                            if first_token is None:
                                first_token = time.monotonic()
                                self._metric("TTFT-real-token", (first_token - start) * 1000, len(event["token"]))
                total_ms = (time.monotonic() - start) * 1000
                self._metric("total-duration", total_ms, len(answer))
                reason = failure_reason(answer, error_event)
                if reason:
                    response.failure(reason)
                elif not (done and answer.strip()):
                    response.failure("no_final_answer")
                else:
                    response.success()
        except Exception as e:                                   # a read gap > READ_TIMEOUT lands here
            name = type(e).__name__
            self.environment.events.request.fire(request_type="POST", name="/query/stream", response_time=(time.monotonic() - start) * 1000,
                                                 response_length=0, exception=Exception("stalled" if "Timeout" in name else name))

    def _metric(self, label, ms, length):
        self.environment.events.request.fire(request_type="POST", name=f"/query/stream [{label}]",
                                             response_time=ms, response_length=length, exception=None)
