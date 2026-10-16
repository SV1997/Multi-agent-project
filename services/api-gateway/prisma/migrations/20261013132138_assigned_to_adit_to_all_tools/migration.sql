-- AlterTable
ALTER TABLE "LegalContract" ADD COLUMN     "assigned_to" TEXT;

-- AlterTable
ALTER TABLE "TICKETS" ADD COLUMN     "assigned_to" TEXT;

-- AddForeignKey
ALTER TABLE "TICKETS" ADD CONSTRAINT "TICKETS_assigned_to_fkey" FOREIGN KEY ("assigned_to") REFERENCES "User"("Email") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LegalContract" ADD CONSTRAINT "LegalContract_assigned_to_fkey" FOREIGN KEY ("assigned_to") REFERENCES "User"("Email") ON DELETE SET NULL ON UPDATE CASCADE;
