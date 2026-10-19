-- CreateTable
CREATE TABLE "doc_extractions" (
    "id" SERIAL NOT NULL,
    "doc_id" TEXT NOT NULL,
    "version" INTEGER NOT NULL,
    "namespace" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "counterparty" TEXT,
    "expiry_date" DATE,
    "value" DECIMAL(18,2),
    "currency" TEXT,
    "auto_renews" BOOLEAN,
    "needs_review" BOOLEAN NOT NULL DEFAULT false,
    "review_reasons" TEXT[],
    "details" JSONB NOT NULL,
    "extracted_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "doc_extractions_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "doc_extractions_doc_id_version_key" ON "doc_extractions"("doc_id", "version");

-- CreateIndex
CREATE INDEX "doc_extractions_namespace_expiry_date_idx" ON "doc_extractions"("namespace", "expiry_date");
