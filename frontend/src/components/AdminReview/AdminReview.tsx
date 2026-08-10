import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { Scale, Users, Cpu, Code2, LifeBuoy, Check, Pencil, Loader2, Inbox } from "lucide-react";
import { fetchRequestGet, fetchRequestPost } from "../../common/NetworkOps";
import ApiObj from "../../common/ApiObj";
import { showToastError, showToastSuccess } from "../../toastMessage/toast";

type Agent = {
  id: string;
  name: string;
  color: string;
  icon: typeof Scale;
};

const AGENTS: Record<string, Agent> = {
  legal_agent: { id: "legal_agent", name: "Legal", color: "#9B8CFF", icon: Scale },
  hr_agent: { id: "hr_agent", name: "HR", color: "#FF8FA3", icon: Users },
  engineering_agent: { id: "engineering_agent", name: "Engineering", color: "#58C4DC", icon: Cpu },
  coding_agent: { id: "coding_agent", name: "Coding", color: "#8DD672", icon: Code2 },
  support_agent: { id: "support_agent", name: "Support", color: "#F2A93C", icon: LifeBuoy },
};

type PendingReviewRow = {
  threadId: string;
  sessionId: string;
  turnId: string;
  domain: string;
  answer: string;
  sources: string[]; // JSON-stringified — parse before rendering
  confidence: number;
  createdAt: string;
};

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const tone =
    confidence < 0.4
      ? "text-red-400 bg-red-400/10 border-red-400/30"
      : confidence < 0.7
      ? "text-amber-400 bg-amber-400/10 border-amber-400/30"
      : "text-emerald-400 bg-emerald-400/10 border-emerald-400/30";

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] ${tone}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {pct}% confidence
    </span>
  );
}

function ReviewCard({ review,setReviews }: { review: PendingReviewRow, setReviews:Dispatch<SetStateAction<PendingReviewRow[]>> }) {
  const agent = AGENTS[review.domain] ?? AGENTS.support_agent;
  const Icon = agent.icon;

  const [draft, setDraft] = useState(review.answer);
  const [submitting, setSubmitting] = useState(false);

  const isEdited = draft.trim() !== review.answer.trim();

  const parsedSources: any[] = (review.sources ?? []).map((s) => {
    try {
      return JSON.parse(s);
    } catch {
      return { path: s };
    }
  });

  const handleApprove = async () => {
    setSubmitting(true);
    try {
        const humanResponse = isEdited?
        {edited:true, revised_answer:draft, approved:true}:
        {edited:false, revised_answer:draft, approved:true};

        const res:any = await fetchRequestPost(ApiObj.query.QUERY_RESOLVE_REVIEW,{threadId:review.threadId, human_response:humanResponse})
        if(res.success){
            showToastSuccess("query has been approved")
            setReviews((prev)=>{
            return prev.filter((r)=>{
                return r.threadId!== review.threadId
            })         
            })
        }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-2xl border border-[#263047] bg-[#131A26] p-5">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div
            className="flex h-8 w-8 items-center justify-center rounded-lg"
            style={{ background: `${agent.color}1F` }}
          >
            <Icon size={15} color={agent.color} strokeWidth={2} />
          </div>
          <div>
            <div className="text-[13px] font-medium text-[#E7E9EE]">{agent.name}</div>
            <div className="font-mono text-[10.5px] text-[#4A5468]">
              thread {review.threadId.slice(0, 8)}
            </div>
          </div>
        </div>
        <ConfidenceBadge confidence={review.confidence} />
      </div>

      {/* Editable answer */}
      <div className="mb-3">
        <label className="mb-1.5 block font-mono text-[10px] tracking-wide text-[#4A5468]">
          DRAFT ANSWER
        </label>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={5}
          className="w-full resize-none rounded-lg border border-[#263047] bg-[#1B2433] p-3 text-[13.5px] leading-relaxed text-[#E7E9EE] outline-none focus:border-[#F2A93C]/50"
        />
        {isEdited && (
          <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-[#F2A93C]">
            <Pencil size={11} />
            Edited from original
          </div>
        )}
      </div>

      {/* Sources */}
      {parsedSources.length > 0 && (
        <div className="mb-4">
          <label className="mb-1.5 block font-mono text-[10px] tracking-wide text-[#4A5468]">
            SOURCES
          </label>
          <div className="flex flex-wrap gap-1.5">
            {parsedSources.map((s, i) => (
              <span
                key={i}
                className="rounded-md border border-[#263047] bg-[#0B0F17] px-2 py-1 font-mono text-[10.5px] text-[#7C8699]"
              >
                {s.path ?? s.source ?? "unknown"}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between border-t border-[#263047] pt-3.5">
        <span className="font-mono text-[10.5px] text-[#4A5468]">
          {new Date(review.createdAt).toLocaleString()}
        </span>
        <button
          onClick={handleApprove}
          disabled={submitting}
          className="flex items-center gap-2 rounded-lg bg-[#F2A93C] px-4 py-2 text-[13px] font-medium text-[#0B0F17] transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              Approving…
            </>
          ) : (
            <>
              <Check size={14} />
              Approve
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl border border-[#263047] bg-[#131A26]">
        <Inbox size={20} className="text-[#4A5468]" />
      </div>
      <div className="mb-1.5 text-[15px] font-medium text-[#E7E9EE]">Queue is clear</div>
      <div className="max-w-[280px] text-[13px] leading-relaxed text-[#7C8699]">
        No answers are waiting on review right now. New ones will show up here as agents flag them.
      </div>
    </div>
  );
}

export default function AdminReviewQueue() {
  // TODO: replace with real fetch — GET /query/pending-reviews
  const [reviews, setReviews] = useState<PendingReviewRow[]>([]);
  const [loading, setLoading] = useState(false);
    useEffect(()=>{
        async function fetchReviews(){
            try {
                setLoading(true)
            const reviews:any =await  fetchRequestGet(ApiObj.query.QUERY_PENDING_REVIEWS);
            console.log(reviews);
            
            setReviews(reviews)
            setLoading(false)
        }
        catch{
            showToastError("error in fetching review")
        }
        }
        fetchReviews()
    },[])
  return (
    <div className="min-h-screen bg-[#0B0F17] px-8 py-10">
      <div className="mx-auto max-w-3xl">
        <div className="mb-8">
          <h1 className="text-[20px] font-semibold text-[#E7E9EE]">Review queue</h1>
          <p className="mt-1 text-[13px] text-[#7C8699]">
            {reviews.length > 0
              ? `${reviews.length} answer${reviews.length === 1 ? "" : "s"} waiting on your approval`
              : "Answers flagged by agents for review appear here"}
          </p>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-24">
            <Loader2 size={20} className="animate-spin text-[#4A5468]" />
          </div>
        )}

        {!loading && reviews.length === 0 && <EmptyState />}

        {!loading && reviews.length > 0 && (
          <div className="flex flex-col gap-4">
            {reviews.map((r) => (
              <ReviewCard key={r.threadId} setReviews={setReviews} review={r} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}