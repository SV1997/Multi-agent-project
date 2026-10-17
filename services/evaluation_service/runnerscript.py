import json
import requests
import time

ORCHESTRATOR_URL = "http://127.0.0.1:8003/api/v1/query"
INTERNAL_SECRET = "dev-secret-change-in-prod"

with open("test_questions.json") as f:
    questions = json.load(f)

results = []

def call_orchestrator(payload, headers, max_retries=3):
    for attempt in range(max_retries):
        response = requests.post(ORCHESTRATOR_URL, json=payload, headers=headers)
        if response.status_code == 429:
            wait = 15 * (attempt + 1)
            print(f"Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        return response
    raise Exception(f"Max retries exceeded for: {payload['query'][:50]}")

for q in questions:
    print(f"Running Q{q['id']}: {q['question'][:50]}...")

    payload = {
        "query": q["question"],
        "allowed_namespace": [q["namespace"]]
    }

    try:
        response = call_orchestrator(payload, {"x-internal-secret": INTERNAL_SECRET})
        data = response.json()
    except Exception as e:
        print(f"FAILED Q{q['id']}: {e}")
        results.append({
            "question": q["question"],
            "answer": "",
            "contexts": [],
            "sources": [],
            "error": str(e),
            "namespace": q["namespace"],
            "ground_truth": q.get("ground_truth"),
            "confidence": None,
            "requires_human_review": None
        })
        # save progress even after a failure, then move to next question
        with open("ragas_results.json", "w") as f:
            json.dump(results, f, indent=2)
        time.sleep(10)
        continue  # skip the rest of this iteration, go to next question

    if data.get("status") == "paused_for_review":
        review = data["review_payload"][0]
        answer_text = review["answer"]["answer"]
        sources = review["answer"].get("sources", [])
        contexts = review.get("context", [])
        confidence = review["answer"]["confidence"]
        requires_review = True
    else:
        answer_text = data.get("answer", "")
        contexts = data.get("context", [])
        sources = data.get("sources", [])
        confidence = data.get("confidence")
        requires_review = data.get("requires_human_review", False)

    results.append({
        "question": q["question"],
        "answer": answer_text,
        "sources": [str(s) for s in sources],
        "contexts": contexts,
        "ground_truth": q.get("ground_truth"),
        "namespace": q["namespace"],
        "confidence": confidence,
        "requires_human_review": requires_review
    })

    # save progress after EVERY question, not just at the end
    with open("ragas_results.json", "w") as f:
        json.dump(results, f, indent=2)

    time.sleep(10)

print(f"Done. {len(results)} results saved to ragas_results.json")