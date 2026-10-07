/*
  Warnings:

  - A unique constraint covering the columns `[claim_id]` on the table `ExpenseClaim` will be added. If there are existing duplicate values, this will fail.

*/
-- CreateTable
CREATE TABLE "ExpenseReview" (
    "id" SERIAL NOT NULL,
    "reason" TEXT NOT NULL,
    "reviewedByUser" TEXT NOT NULL,
    "claim" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ExpenseReview_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "ExpenseClaim_claim_id_key" ON "ExpenseClaim"("claim_id");

-- AddForeignKey
ALTER TABLE "ExpenseReview" ADD CONSTRAINT "ExpenseReview_reviewedByUser_fkey" FOREIGN KEY ("reviewedByUser") REFERENCES "User"("Email") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ExpenseReview" ADD CONSTRAINT "ExpenseReview_claim_fkey" FOREIGN KEY ("claim") REFERENCES "ExpenseClaim"("claim_id") ON DELETE RESTRICT ON UPDATE CASCADE;
