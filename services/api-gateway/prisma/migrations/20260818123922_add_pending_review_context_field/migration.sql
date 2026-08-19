-- AlterTable
ALTER TABLE "PendingReview" ADD COLUMN     "context" TEXT[] DEFAULT ARRAY[]::TEXT[];
