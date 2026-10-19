-- CreateTable
CREATE TABLE "bm25_indexes" (
    "namespace" TEXT NOT NULL,
    "indexData" BYTEA NOT NULL,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "bm25_indexes_pkey" PRIMARY KEY ("namespace")
);
