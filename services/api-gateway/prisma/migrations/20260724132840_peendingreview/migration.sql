-- CreateTable
CREATE TABLE "PendingReview" (
    "id" SERIAL NOT NULL,
    "thread_id" TEXT NOT NULL,
    "userId" INTEGER NOT NULL,
    "sources" TEXT NOT NULL,
    "answer" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL,
    "created_At" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "resolved" BOOLEAN NOT NULL DEFAULT false,
    "resolvedAt" TIMESTAMP(3),

    CONSTRAINT "PendingReview_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "PendingReview_thread_id_key" ON "PendingReview"("thread_id");

-- AddForeignKey
ALTER TABLE "PendingReview" ADD CONSTRAINT "PendingReview_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
