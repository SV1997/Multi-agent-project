-- AlterTable
ALTER TABLE "PendingReview" ADD COLUMN     "Flagged" BOOLEAN,
ADD COLUMN     "answerRelevancyScore" DOUBLE PRECISION,
ADD COLUMN     "evaluatedAt" TIMESTAMP(3),
ADD COLUMN     "faithfulnescore" DOUBLE PRECISION;
