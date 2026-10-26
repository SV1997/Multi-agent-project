-- AlterTable
ALTER TABLE "ExpenseClaim" ADD COLUMN     "assigned_to" TEXT;

-- AddForeignKey
ALTER TABLE "ExpenseClaim" ADD CONSTRAINT "ExpenseClaim_assigned_to_fkey" FOREIGN KEY ("assigned_to") REFERENCES "User"("Email") ON DELETE RESTRICT ON UPDATE CASCADE;
