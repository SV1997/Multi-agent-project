Step	Node or edge	What happens	Model call?
1	START → manage_context	Summarises older turns only when the split rule says so (after 12 user turns). Uses the ledger and guard_notes.	Only on summary turns (gpt-oss-120b, high effort)
1b	START → retrieve_memories (runs in parallel)	Searches the Postgres memory store for this employee’s top 3 facts. Skipped if DISABLE_LONG_TERM_MEMORY=1.	No, it is an embedding search
2	both → classify_domain	Picks one word: legal, hr, engineering, finance or support.	Yes (1)
3	conditional edge route_after_classification	ok → check_authorization. failed → classification_failed, which asks the user to rephrase and ends.	No
4	check_authorization	Compares the domain with allowed_namespace.	No
5	conditional edge route_to_agent	Goes to legal_agent, hr_agent, finance_agent, support_agent or engineering_agent. If not allowed, goes to access_denied, then ends.	No

C. Inside the domain agent (agent_factory.py)

Step	Node or edge	What happens	Model call?
6	prepare_retrieval	Resets state. Max retrieval attempts is 3.	No
7	plan_retrieval	Picks one source: sql, vector or none. Memory facts are checked first.	Yes (2)
8	conditional edge route_after_planning	vector → retrieve. sql → sql_retrieval. none → reason.	No

Vector path

Step	Node or edge	What happens	Model call?
9	retrieve	Calls the retrieval service with the domain namespace and top_k 5.	No
10	inside retrieval	Embeds the query (text-embedding-3-small), searches Pinecone, loads the BM25 index from Postgres, merges with RRF, and applies the cross-encoder only if RERANK_ENABLED is true (it is false by default).	Embedding only
11	retrieve → grade_retrieval	Marks the evidence relevant or insufficient and says whether a live tool can answer.	Yes (3)
12	conditional edge route_after_grading	Relevant → reason. Insufficient and attempts left → rewrite_query → retrieve (+2 calls). Attempts used up → fallback_to_sql → sql_retrieval (once). Otherwise → insufficient_evidence, which answers “I couldn’t find enough relevant information” and ends.	rewrite_query is a call

SQL path

Step	Node or edge	What happens	Model call?
9	sql_retrieval	The model picks one fixed function and its params. The retrieval service runs it using employee_email.	Yes (3)
10	conditional edge route_after_sql	Result OK → reason. Error → fallback_to_vector → retrieve (once), or insufficient_evidence.	No

Answering

Step	Node or edge	What happens	Model call?
13	reason	Builds the prompt from the context, applying edge_order (ranks 1,3,5,4,2) if CONTEXT_REORDER is on. The model either answers or calls a tool.	Yes (4)
14	conditional edge route_after_reason	Tool call → tools → back to reason (+1 call per round). Budget is 6 rounds when streaming. No tool call → end.	+1 per round
15	_finalize_answer (inside reason)	A structured call returns confidence, requires_human_review and conflict_detected. Review is requires_human_review OR conflict_detected.	Yes (5)

D. Back in the supervisor

Step	Node or edge	What happens	Model call?
16	each agent → human_review_gate	If review is required, interrupt() pauses the graph and the gateway returns paused_for_review. An admin approves or edits through /resume or /resolve-review (RoleguardGuard).	No
17	human_review_gate → extract_memories → END	Runs in the background. Skipped if confidence is 0.3 or below. Saves employee-specific facts to the memory store.	Yes (6, in the background)