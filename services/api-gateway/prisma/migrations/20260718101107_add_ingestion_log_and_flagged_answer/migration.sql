-- CreateTable
CREATE TABLE "IngestionLog" (
    "id" SERIAL NOT NULL,
    "user_id" INTEGER NOT NULL,
    "namespace" TEXT NOT NULL,
    "sources" JSONB NOT NULL,
    "status" TEXT NOT NULL,
    "created_At" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "IngestionLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "FlaggedAnswer" (
    "id" SERIAL NOT NULL,
    "flaggedByUserId" INTEGER NOT NULL,
    "domain" TEXT NOT NULL,
    "answer" TEXT NOT NULL,
    "Sources" JSONB NOT NULL,
    "reason" TEXT,
    "created_At" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "FlaggedAnswer_pkey" PRIMARY KEY ("id")
);

-- AddForeignKey
ALTER TABLE "IngestionLog" ADD CONSTRAINT "IngestionLog_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FlaggedAnswer" ADD CONSTRAINT "FlaggedAnswer_flaggedByUserId_fkey" FOREIGN KEY ("flaggedByUserId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
