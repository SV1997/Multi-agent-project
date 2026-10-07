/*
  Warnings:

  - Added the required column `leave_type` to the `LeaveRecord` table without a default value. This is not possible if the table is not empty.
  - Added the required column `reason` to the `LeaveRecord` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "LeaveRecord" ADD COLUMN     "leave_type" TEXT NOT NULL,
ADD COLUMN     "reason" TEXT NOT NULL;
