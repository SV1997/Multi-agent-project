import { useEffect, useState } from "react";
import { FileText, Trash2, RefreshCw, Loader2 } from "lucide-react";
import { fetchRequestGet, fetchRequesDelete } from "../../common/NetworkOps";
import ApiObj from "../../common/ApiObj";
import { showToastError, showToastSuccess } from "../../toastMessage/toast";

type IndexedDoc = {
    doc_id: string;
    name: string;
    file: string;
    chunks: number;
    version: number | null;
    ingested_at: string | null;
};

type DocumentsResponse = { documents?: IndexedDoc[] };

// what a finished request left behind: which request it answered, and either its documents or its error
type LoadResult = { key: string; namespace: string; docs: IndexedDoc[]; error: string | null };

// the gateway sends { statusCode, message }; message may be a string or a list
function errorMessage(err: unknown, fallback: string): string {
    const raw = (err as { message?: string | string[] } | null)?.message;
    return (Array.isArray(raw) ? raw.join(", ") : raw) || fallback;
}

function formatDate(iso: string | null): string {
    if (!iso) return "";
    const date = new Date(iso);
    return Number.isNaN(date.getTime())
        ? ""
        : date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function DocumentRow({
    doc,
    confirming,
    deleting,
    onAskDelete,
    onCancel,
    onConfirm,
}: {
    doc: IndexedDoc;
    confirming: boolean;
    deleting: boolean;
    onAskDelete: () => void;
    onCancel: () => void;
    onConfirm: () => void;
}) {
    const details = [
        // the file name tells apart documents that share a title (e.g. several uploads of the same policy)
        doc.file && doc.file !== doc.name ? doc.file : "",
        `${doc.chunks} chunk${doc.chunks === 1 ? "" : "s"}`,
        doc.version ? `v${doc.version}` : "",
        formatDate(doc.ingested_at),
    ].filter(Boolean);

    return (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-[#263047] bg-[#1B2433] px-3.5 py-2.5">
            <div className="flex min-w-0 items-center gap-2.5">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#0B0F17]">
                    <FileText size={13} className="text-[#7C8699]" />
                </div>
                <div className="min-w-0">
                    <div className="truncate text-[13px] text-[#E7E9EE]" title={doc.name}>
                        {doc.name}
                    </div>
                    <div className="font-mono text-[10px] text-[#4A5468]">{details.join(" · ")}</div>
                </div>
            </div>

            {confirming ? (
                <div className="flex shrink-0 items-center gap-2">
                    <span className="text-[12px] text-[#7C8699]">Delete everywhere?</span>
                    <button
                        onClick={onConfirm}
                        disabled={deleting}
                        className="flex items-center gap-1.5 rounded-md border border-red-400/40 bg-red-400/10 px-2.5 py-1 text-[12px] font-medium text-red-400 transition-colors hover:bg-red-400/20 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        {deleting && <Loader2 size={12} className="animate-spin" />}
                        {deleting ? "Deleting…" : "Delete"}
                    </button>
                    <button
                        onClick={onCancel}
                        disabled={deleting}
                        className="rounded-md px-2 py-1 text-[12px] text-[#7C8699] transition-colors hover:text-[#E7E9EE] disabled:opacity-60"
                    >
                        Cancel
                    </button>
                </div>
            ) : (
                <button
                    onClick={onAskDelete}
                    aria-label={`Delete ${doc.name}`}
                    title="Delete this document"
                    className="shrink-0 rounded-md p-1.5 text-[#4A5468] transition-colors hover:bg-[#263047] hover:text-red-400"
                >
                    <Trash2 size={14} />
                </button>
            )}
        </div>
    );
}

export default function IndexedDocuments({ namespace, refreshKey }: { namespace: string; refreshKey: number }) {
    const [result, setResult] = useState<LoadResult | null>(null);
    const [reloadTick, setReloadTick] = useState(0);
    const [confirmId, setConfirmId] = useState<string | null>(null);
    const [deletingId, setDeletingId] = useState<string | null>(null);

    // Every namespace / upload / Refresh click is a new request key. The list is "loading" until a result
    // for the CURRENT key has arrived, so a slow response for an old namespace can never overwrite a newer one.
    const requestKey = `${namespace}|${refreshKey}|${reloadTick}`;
    const loading = !!namespace && result?.key !== requestKey;
    const docs = result && result.namespace === namespace ? result.docs : [];   // keep showing the old list while refreshing the same namespace
    const error = result?.key === requestKey ? result.error : null;

    useEffect(() => {
        if (!namespace) return;
        let cancelled = false;
        fetchRequestGet(`${ApiObj.ingestion.DOCUMENTS}?namespace=${encodeURIComponent(namespace)}`)
            .then((res) => {
                const body = res as unknown as DocumentsResponse;   // the response interceptor already unwraps axios' .data
                if (!cancelled) setResult({ key: requestKey, namespace, docs: body?.documents ?? [], error: null });
            })
            .catch((err: unknown) => {
                if (!cancelled) setResult({ key: requestKey, namespace, docs: [], error: errorMessage(err, "Could not load the documents") });
            });
        return () => {
            cancelled = true;
        };
    }, [namespace, requestKey]);

    const handleDelete = async (doc: IndexedDoc) => {
        setDeletingId(doc.doc_id);
        try {
            await fetchRequesDelete(`${ApiObj.ingestion.DOCUMENT(doc.doc_id)}?namespace=${encodeURIComponent(namespace)}`);
            // Pinecone listings are eventually consistent, so re-fetching right now could show the document
            // again for a moment; drop it locally instead and let "Refresh" reload from the server.
            setResult((prev) => (prev ? { ...prev, docs: prev.docs.filter((d) => d.doc_id !== doc.doc_id) } : prev));
            showToastSuccess(`Deleted ${doc.name}`);
        } catch (err: unknown) {
            showToastError(errorMessage(err, "Failed to delete the document"));
        } finally {
            setDeletingId(null);
            setConfirmId(null);
        }
    };

    const handleRefresh = () => {
        setConfirmId(null);
        setReloadTick((t) => t + 1);
    };

    return (
        <div className="rounded-2xl border border-[#263047] bg-[#131A26] p-5">
            <div className="mb-3 flex items-center justify-between">
                <label className="block font-mono text-[10px] tracking-wide text-[#4A5468]">
                    INDEXED DOCUMENTS{namespace && !loading && !error ? ` (${docs.length})` : ""}
                </label>
                <button
                    onClick={handleRefresh}
                    disabled={loading || !namespace}
                    className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[12px] text-[#7C8699] transition-colors hover:text-[#E7E9EE] disabled:cursor-not-allowed disabled:opacity-40"
                >
                    <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
                    Refresh
                </button>
            </div>

            {!namespace && <p className="text-[12.5px] text-[#4A5468]">Select a namespace to see its documents.</p>}

            {loading && docs.length === 0 && (
                <div className="flex items-center gap-2 py-4 text-[12.5px] text-[#7C8699]">
                    <Loader2 size={14} className="animate-spin" />
                    Loading documents…
                </div>
            )}

            {error && (
                <div className="rounded-lg border border-red-400/30 bg-red-400/10 px-3.5 py-2.5 text-[12.5px] text-red-400">
                    {error}
                </div>
            )}

            {namespace && !loading && !error && docs.length === 0 && (
                <p className="py-2 text-[12.5px] text-[#4A5468]">No documents in this namespace yet.</p>
            )}

            {docs.length > 0 && (
                <div className="flex flex-col gap-2">
                    {docs.map((doc) => (
                        <DocumentRow
                            key={doc.doc_id}
                            doc={doc}
                            confirming={confirmId === doc.doc_id}
                            deleting={deletingId === doc.doc_id}
                            onAskDelete={() => setConfirmId(doc.doc_id)}
                            onCancel={() => setConfirmId(null)}
                            onConfirm={() => handleDelete(doc)}
                        />
                    ))}
                </div>
            )}

            {namespace && (
                <p className="mt-3 text-[11.5px] text-[#4A5468]">
                    Deleting removes the document from search entirely. New uploads can take a few seconds to appear; use Refresh.
                </p>
            )}
        </div>
    );
}
