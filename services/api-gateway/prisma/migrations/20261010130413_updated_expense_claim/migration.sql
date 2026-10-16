-- DropForeignKey
ALTER TABLE "ExpenseClaim" DROP CONSTRAINT "ExpenseClaim_assigned_to_fkey";

-- AddForeignKey
ALTER TABLE "ExpenseClaim" ADD CONSTRAINT "ExpenseClaim_assigned_to_fkey" FOREIGN KEY ("assigned_to") REFERENCES "User"("Email") ON DELETE SET NULL ON UPDATE CASCADE;
