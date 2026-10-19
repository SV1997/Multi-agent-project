/*
  Warnings:

  - Made the column `assigned_to` on table `ExpenseClaim` required. This step will fail if there are existing NULL values in that column.

*/
-- DropForeignKey
ALTER TABLE "ExpenseClaim" DROP CONSTRAINT "ExpenseClaim_assigned_to_fkey";

-- AlterTable
ALTER TABLE "ExpenseClaim" ALTER COLUMN "assigned_to" SET NOT NULL;

-- AddForeignKey
ALTER TABLE "ExpenseClaim" ADD CONSTRAINT "ExpenseClaim_assigned_to_fkey" FOREIGN KEY ("assigned_to") REFERENCES "User"("Email") ON DELETE RESTRICT ON UPDATE CASCADE;
