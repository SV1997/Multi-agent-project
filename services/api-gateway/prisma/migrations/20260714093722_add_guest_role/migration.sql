-- AlterEnum
ALTER TYPE "Role" ADD VALUE 'guest';

-- AlterTable
ALTER TABLE "User" ALTER COLUMN "role" SET DEFAULT 'guest';
