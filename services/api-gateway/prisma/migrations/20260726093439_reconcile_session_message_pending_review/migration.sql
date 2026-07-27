-- Reconciles drift where the dev database had columns (domain, sessionId, turnId on
-- PendingReview) added out-of-band via `db push`, without the Session/Message tables
-- that the current schema expects them to relate to.
--
-- Written to be safe both against the already-drifted dev database (where domain/
-- sessionId/turnId already exist and sources is already jsonb) and against a clean
-- replay of migration history from scratch (shadow database, CI, a new environment),
-- where none of that drift is present and sources is still text[].

-- CreateTable
CREATE TABLE IF NOT EXISTS "Session" (
    "id" TEXT NOT NULL,
    "thread_id" TEXT NOT NULL,
    "userId" INTEGER NOT NULL,
    "created_At" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Session_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE IF NOT EXISTS "Message" (
    "id" TEXT NOT NULL,
    "sessionId" TEXT NOT NULL,
    "role" "Role" NOT NULL,
    "content" TEXT NOT NULL,
    "turnId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Message_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX IF NOT EXISTS "Session_thread_id_key" ON "Session"("thread_id");

-- AddForeignKey (guarded: no-op if this migration is being re-run after a partial failure)
DO $$ BEGIN
  ALTER TABLE "Session" ADD CONSTRAINT "Session_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  ALTER TABLE "Message" ADD CONSTRAINT "Message_sessionId_fkey" FOREIGN KEY ("sessionId") REFERENCES "Session"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Ensure PendingReview has the columns that were previously added out-of-band on the
-- real dev database. On a clean replay these don't exist yet, so create them here with
-- the same placeholder defaults the earlier out-of-band `db push` used.
ALTER TABLE "PendingReview" ADD COLUMN IF NOT EXISTS "domain" TEXT NOT NULL DEFAULT 'guest';
ALTER TABLE "PendingReview" ADD COLUMN IF NOT EXISTS "sessionId" TEXT NOT NULL DEFAULT 'placeholder_session_id';

-- Normalize `sources` to nullable jsonb regardless of its starting representation:
-- text[] (from migration history) or jsonb (from the earlier out-of-band db push).
DO $$
DECLARE
  col_type text;
BEGIN
  SELECT data_type INTO col_type FROM information_schema.columns
  WHERE table_name = 'PendingReview' AND column_name = 'sources';

  IF col_type = 'ARRAY' THEN
    ALTER TABLE "PendingReview" ALTER COLUMN "sources" DROP NOT NULL;
    ALTER TABLE "PendingReview" ALTER COLUMN "sources" TYPE JSONB USING to_jsonb("sources");
  END IF;
END $$;

-- Backfill a Session row for the existing PendingReview rows that carry the
-- "placeholder_session_id" value, so the new foreign key below doesn't orphan them.
INSERT INTO "Session" ("id", "thread_id", "userId", "created_At", "updatedAt")
SELECT 'placeholder_session_id', 'placeholder_thread_id', pr."userId", CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM "PendingReview" pr
WHERE pr."sessionId" = 'placeholder_session_id'
LIMIT 1
ON CONFLICT ("id") DO NOTHING;

-- Rename PendingReview columns to match current schema
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'PendingReview' AND column_name = 'thread_id') THEN
    ALTER TABLE "PendingReview" RENAME COLUMN "thread_id" TO "threadId";
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'PendingReview' AND column_name = 'created_At') THEN
    ALTER TABLE "PendingReview" RENAME COLUMN "created_At" TO "createdAt";
  END IF;
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'PendingReview_thread_id_key') THEN
    ALTER INDEX "PendingReview_thread_id_key" RENAME TO "PendingReview_threadId_key";
  END IF;
END $$;

-- Drop the stray turnId placeholder column if present (superseded by Message.turnId)
ALTER TABLE "PendingReview" DROP COLUMN IF EXISTS "turnId";

-- Tighten columns to match schema (no NULLs / placeholder defaults exist to lose)
ALTER TABLE "PendingReview" ALTER COLUMN "sources" SET NOT NULL;
ALTER TABLE "PendingReview" ALTER COLUMN "sessionId" DROP DEFAULT;
ALTER TABLE "PendingReview" ALTER COLUMN "domain" DROP DEFAULT;

-- AddForeignKey
DO $$ BEGIN
  ALTER TABLE "PendingReview" ADD CONSTRAINT "PendingReview_sessionId_fkey" FOREIGN KEY ("sessionId") REFERENCES "Session"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
