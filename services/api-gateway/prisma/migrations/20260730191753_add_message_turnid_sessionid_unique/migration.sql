-- CreateIndex
CREATE UNIQUE INDEX "Message_turnId_sessionId_role_key" ON "Message"("turnId", "sessionId", "role");
