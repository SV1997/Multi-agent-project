import { useRef, useState } from "react";
import { Link2, FileText, FileCode, Plus, X, UploadCloud, Loader2, CheckCircle2 } from "lucide-react";
import { jwtDecode } from "jwt-decode";
import { fetchRequestPost, fetchRequestPostFormData } from "../../common/NetworkOps";
import ApiObj from "../../common/ApiObj";
import { showToastError, showToastSuccess } from "../../toastMessage/toast";

type SourceType = "pdf" | "url" | "markdown";

type SourceItem = {
    id: string; // client-side only, for list rendering — not sent to backend
    path: string; // URL string for "url" sources, file name for display of "pdf"/"markdown" sources
    type: SourceType;
    file?: File; // present for "pdf"/"markdown" sources, uploaded via multipart
};

// Mirrors the backend's ROLE_NAMESPACE_ACCESS map — for UX filtering only.
// The real check always happens server-side in IngestionService.
const ROLE_NAMESPACE_ACCESS: Record<string, string[]> = {
    legal_team: ["legal"],
    hr_team: ["hr"],
    engineering_team: ["engineering", "coding"],
    support_team: ["support"],
    admin: ["legal", "hr", "engineering", "coding", "support"],
};

const NAMESPACE_LABELS: Record<string, string> = {
    legal: "Legal",
    hr: "HR",
    engineering: "Engineering",
    coding: "Coding",
    support: "Support",
};

const TYPE_CONFIG: Record<SourceType, { label: string; icon: typeof Link2; placeholder: string }> = {
    url: { label: "URL", icon: Link2, placeholder: "https://example.com/policy-doc" },
    pdf: { label: "PDF", icon: FileText, placeholder: "/path/to/document.pdf" },
    markdown: { label: "Markdown", icon: FileCode, placeholder: "/path/to/notes.md" },
};

function TypeTab({
    type,
    active,
    onClick,
}: {
    type: SourceType;
    active: boolean;
    onClick: () => void;
}) {
    const { label, icon: Icon } = TYPE_CONFIG[type];
    return (
        <button
            onClick={onClick}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition-colors ${active
                    ? "border-[#F2A93C]/40 bg-[#F2A93C]/10 text-[#F2A93C]"
                    : "border-[#263047] bg-transparent text-[#7C8699] hover:text-[#E7E9EE]"
                }`}
        >
            <Icon size={13} />
            {label}
        </button>
    );
}

function SourceRow({ source, onRemove }: { source: SourceItem; onRemove: () => void }) {
    const { icon: Icon, label } = TYPE_CONFIG[source.type];
    
    return (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-[#263047] bg-[#1B2433] px-3.5 py-2.5">
            <div className="flex min-w-0 items-center gap-2.5">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#0B0F17]">
                    <Icon size={13} className="text-[#7C8699]" />
                </div>
                <div className="min-w-0">
                    <div className="truncate text-[13px] text-[#E7E9EE]">{source.path}</div>
                    <div className="font-mono text-[10px] text-[#4A5468]">{label}</div>
                </div>
            </div>
            <button
                onClick={onRemove}
                className="shrink-0 rounded-md p-1.5 text-[#4A5468] transition-colors hover:bg-[#263047] hover:text-[#E7E9EE]"
            >
                <X size={14} />
            </button>
        </div>
    );
}

export default function IngestionForm() {

    const token = localStorage.getItem("accessToken") || "";
    const userRole = jwtDecode<{ role: string }>(token).role;
    const allowedNamespaces = ROLE_NAMESPACE_ACCESS[userRole] ?? [];

    const [namespace, setNamespace] = useState<string>(allowedNamespaces[0] ?? "");
    const [activeType, setActiveType] = useState<SourceType>("url");
    const [pathInput, setPathInput] = useState("");
    const [queue, setQueue] = useState<SourceItem[]>([]);
    const [submitting, setSubmitting] = useState(false);
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleAddSource = () => {
        const trimmed = pathInput.trim();
        if (!trimmed) return;
        if (activeType === "url") {
            try {
                const url = new URL(trimmed);
                if (!url.hostname || !["http:", "https:"].includes(url.protocol)) throw new Error();
            } catch {
                setError("Enter a valid HTTP or HTTPS URL.");
                return;
            }
        }
        setQueue((prev) => [...prev, { id: crypto.randomUUID(), path: trimmed, type: activeType }]);
        setPathInput("");
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;
        // extract into a plain array before resetting e.target.value below —
        // e.target.files is tied to the live input and gets cleared once value is reset
        const newItems = Array.from(files).map((file) => ({
            id: crypto.randomUUID(),
            path: file.name,
            type: activeType,
            file,
        }));
        setError(null);
        setQueue((prev) => [...prev, ...newItems]);
        e.target.value = ""; // allow re-selecting the same file(s)
    };
    const handleRemoveSource = (id: string) => {
        setQueue((prev) => prev.filter((s) => s.id !== id));
    };

    const handleSubmit = async () => {
        if (queue.length === 0 || !namespace) return;
        setSubmitting(true);
        setError(null);
        try {
            const urlItems = queue.filter((q) => q.type === "url");
            const fileItems = queue.filter((q) => q.file);

            if (urlItems.length > 0) {
                const payload = { namespace, source: urlItems.map((q) => ({ path: q.path, type: q.type })) };
                const res: any = await fetchRequestPost(ApiObj.ingestion.INGESTION, payload);
                if (!res.success) throw new Error("namespace not allowed for role");
            }

            // the upload endpoint takes one `type` per request, so files of different
            // types (pdf vs. markdown) must be sent as separate requests
            const fileItemsByType = fileItems.reduce<Record<string, SourceItem[]>>((acc, q) => {
                (acc[q.type] ??= []).push(q);
                return acc;
            }, {});

            for (const [type, items] of Object.entries(fileItemsByType)) {
                const formData = new FormData();
                formData.append("namespace", namespace);
                formData.append("type", type);
                items.forEach((q) => formData.append("file", q.file as File));
                const res: any = await fetchRequestPostFormData(ApiObj.ingestion.UPLOAD, formData);
                if (!res.success) throw new Error("namespace not allowed for role");
            }

            setQueue([]);
            setSuccess(true);
            showToastSuccess("source updated successfully");
        } catch (err: any) {
            showToastError(err?.message || "Failed to add sources");
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="min-h-screen bg-[#0B0F17] px-8 py-10">
            <div className="mx-auto max-w-2xl">
                <div className="mb-8">
                    <h1 className="text-[20px] font-semibold text-[#E7E9EE]">Add knowledge</h1>
                    <p className="mt-1 text-[13px] text-[#7C8699]">
                        Documents you add here become searchable by the agents in the namespace you choose.
                    </p>
                </div>

                <div className="rounded-2xl border border-[#263047] bg-[#131A26] p-5">
                    {/* Namespace selector */}
                    <div className="mb-5">
                        <label className="mb-1.5 block font-mono text-[10px] tracking-wide text-[#4A5468]">
                            NAMESPACE
                        </label>
                        <div className="flex flex-wrap gap-2">
                           
                                <select
                                    value={namespace}
                                    onChange={(e) => setNamespace(e.target.value)}
                                    className="w-full rounded-lg border border-[#263047] bg-[#1B2433] px-3.5 py-2.5 text-[13.5px] text-[#E7E9EE] outline-none focus:border-[#F2A93C]/50"
                                >
                                    <option value="" disabled>
                                        Select a namespace
                                    </option>
                                    {allowedNamespaces.map((ns) => (
                                        <option key={ns} value={ns}>
                                            {NAMESPACE_LABELS[ns] ?? ns}
                                        </option>
                                    ))}
                                </select>
                            
                        </div>
                        {allowedNamespaces.length === 0 && (
                            <p className="mt-1.5 text-[12px] text-[#4A5468]">
                                Your role isn't permitted to add knowledge to any namespace.
                            </p>
                        )}
                    </div>

                    {/* Source type + input */}
                    <div className="mb-4">
                        <label className="mb-1.5 block font-mono text-[10px] tracking-wide text-[#4A5468]">
                            SOURCE TYPE
                        </label>
                        <div className="mb-3 flex gap-2">
                            {(Object.keys(TYPE_CONFIG) as SourceType[]).map((t) => (
                                <TypeTab key={t} type={t} active={activeType === t} onClick={() => setActiveType(t)} />
                            ))}
                        </div>

                        <div className="flex gap-2">
                            {activeType === "url" ? (
                                <>
                                    <input
                                        key="url-input"
                                        value={pathInput}
                                        onChange={(e) => setPathInput(e.target.value)}
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter") {
                                                e.preventDefault();
                                                handleAddSource();
                                            }
                                        }}
                                        placeholder={TYPE_CONFIG[activeType].placeholder}
                                        className="flex-1 rounded-lg border border-[#263047] bg-[#1B2433] px-3.5 py-2.5 text-[13.5px] text-[#E7E9EE] outline-none placeholder:text-[#4A5468] focus:border-[#F2A93C]/50"
                                    />
                                    <button
                                        onClick={handleAddSource}
                                        disabled={!pathInput.trim()}
                                        className="flex items-center gap-1.5 rounded-lg bg-[#1B2433] border border-[#263047] px-3.5 text-[13px] font-medium text-[#E7E9EE] transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
                                    >
                                        <Plus size={15} />
                                        Add
                                    </button>
                                </>
                            ) : (
                                <>
                                    <input
                                        key="file-input"
                                        ref={fileInputRef}
                                        type="file"
                                        multiple
                                        accept={activeType === "pdf" ? ".pdf,application/pdf" : ".md,.markdown,text/markdown"}
                                        onChange={handleFileChange}
                                        className="hidden"
                                    />
                                    <button
                                        onClick={() => fileInputRef.current?.click()}
                                        className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-dashed border-[#263047] bg-[#1B2433] py-2.5 text-[13px] font-medium text-[#7C8699] transition-colors hover:text-[#E7E9EE]"
                                    >
                                        <UploadCloud size={15} />
                                        Choose {TYPE_CONFIG[activeType].label} file(s)
                                    </button>
                                </>
                            )}
                        </div>
                    </div>

                    {/* Queued sources */}
                    {queue.length > 0 && (
                        <div className="mb-5">
                            <label className="mb-1.5 block font-mono text-[10px] tracking-wide text-[#4A5468]">
                                QUEUED ({queue.length})
                            </label>
                            <div className="flex flex-col gap-2">
                                {queue.map((s) => (
                                    <SourceRow key={s.id} source={s} onRemove={() => handleRemoveSource(s.id)} />
                                ))}
                            </div>
                        </div>
                    )}

                    {error && (
                        <div className="mb-4 rounded-lg border border-red-400/30 bg-red-400/10 px-3.5 py-2.5 text-[12.5px] text-red-400">
                            {error}
                        </div>
                    )}

                    {success && (
                        <div className="mb-4 flex items-center gap-2 rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3.5 py-2.5 text-[12.5px] text-emerald-400">
                            <CheckCircle2 size={14} />
                            Added to the {NAMESPACE_LABELS[namespace] ?? namespace} namespace
                        </div>
                    )}

                    {/* Submit */}
                    <button
                        onClick={handleSubmit}
                        disabled={submitting || queue.length === 0 || !namespace}
                        className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#F2A93C] py-2.5 text-[13.5px] font-medium text-[#0B0F17] transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
                    >
                        {submitting ? (
                            <>
                                <Loader2 size={15} className="animate-spin" />
                                Adding…
                            </>
                        ) : (
                            <>
                                <UploadCloud size={15} />
                                Add {queue.length > 0 ? `${queue.length} source${queue.length === 1 ? "" : "s"}` : "sources"}
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
}
