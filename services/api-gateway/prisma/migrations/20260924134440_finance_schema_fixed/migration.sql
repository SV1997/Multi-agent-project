-- CreateEnum
CREATE TYPE "ClaimStatus" AS ENUM ('pending', 'approved', 'rejected', 'flagged');

-- CreateTable
CREATE TABLE "ExpenseClaim" (
    "id" SERIAL NOT NULL,
    "claim_id" TEXT NOT NULL,
    "employee_email" TEXT NOT NULL,
    "amount" DECIMAL(65,30) NOT NULL,
    "status" "ClaimStatus" NOT NULL,
    "submitted_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ExpenseClaim_pkey" PRIMARY KEY ("id")
);

-- AddForeignKey
ALTER TABLE "ExpenseClaim" ADD CONSTRAINT "ExpenseClaim_employee_email_fkey" FOREIGN KEY ("employee_email") REFERENCES "User"("Email") ON DELETE RESTRICT ON UPDATE CASCADE;
