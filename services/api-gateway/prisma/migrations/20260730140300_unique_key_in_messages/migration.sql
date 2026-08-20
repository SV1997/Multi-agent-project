/*
  Warnings:

  - A unique constraint covering the columns `[sessionId,role,turnId]` on the table `Message` will be added. If there are existing duplicate values, this will fail.

*/
-- DropIndex
DROP INDEX IF EXISTS "Message_turnId_sessionId_role_key";

-- CreateIndex
CREATE UNIQUE INDEX "Message_sessionId_role_turnId_key" ON "Message"("sessionId", "role", "turnId");
