-- CreateEnum
CREATE TYPE "Status" AS ENUM ('pending', 'resolved', 'rejected');

-- AlterTable
ALTER TABLE "TICKETS" ADD COLUMN     "status" "Status" NOT NULL DEFAULT 'pending';
