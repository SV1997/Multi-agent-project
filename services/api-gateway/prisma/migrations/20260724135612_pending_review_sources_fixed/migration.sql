/*
  Warnings:

  - The `sources` column on the `PendingReview` table would be dropped and recreated. This will lead to data loss if there is data in the column.

*/
-- AlterTable
ALTER TABLE "PendingReview" DROP COLUMN "sources",
ADD COLUMN     "sources" TEXT[];
