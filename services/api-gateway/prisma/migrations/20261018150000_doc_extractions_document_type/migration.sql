-- AlterTable: existing rows get 'unknown' (they were extracted before document types existed)
ALTER TABLE "doc_extractions" ADD COLUMN     "document_type" TEXT NOT NULL DEFAULT 'unknown';
