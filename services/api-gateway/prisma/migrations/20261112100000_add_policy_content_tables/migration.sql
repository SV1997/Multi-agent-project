-- CreateTable
CREATE TABLE "content_version" (
    "id" SERIAL NOT NULL,
    "version_number" INTEGER NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "content_version_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "category" (
    "version_id" INTEGER NOT NULL,
    "domain" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "position" INTEGER NOT NULL,

    CONSTRAINT "category_pkey" PRIMARY KEY ("version_id","domain","name")
);

-- CreateTable
CREATE TABLE "category_parent" (
    "version_id" INTEGER NOT NULL,
    "domain" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "parent_name" TEXT NOT NULL,
    "position" INTEGER NOT NULL,

    CONSTRAINT "category_parent_pkey" PRIMARY KEY ("version_id","domain","name","parent_name")
);

-- CreateTable
CREATE TABLE "frame" (
    "version_id" INTEGER NOT NULL,
    "frame_id" TEXT NOT NULL,
    "domain" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "position" INTEGER NOT NULL,

    CONSTRAINT "frame_pkey" PRIMARY KEY ("version_id","frame_id")
);

-- CreateTable
CREATE TABLE "frame_category" (
    "version_id" INTEGER NOT NULL,
    "frame_id" TEXT NOT NULL,
    "category_name" TEXT NOT NULL,
    "position" INTEGER NOT NULL,

    CONSTRAINT "frame_category_pkey" PRIMARY KEY ("version_id","frame_id","category_name")
);

-- CreateTable
CREATE TABLE "document" (
    "version_id" INTEGER NOT NULL,
    "domain" TEXT NOT NULL,
    "file_name" TEXT NOT NULL,
    "title" TEXT,
    "position" INTEGER NOT NULL,

    CONSTRAINT "document_pkey" PRIMARY KEY ("version_id","domain","file_name")
);

-- CreateTable
CREATE TABLE "document_category" (
    "version_id" INTEGER NOT NULL,
    "domain" TEXT NOT NULL,
    "file_name" TEXT NOT NULL,
    "category_name" TEXT NOT NULL,
    "position" INTEGER NOT NULL,

    CONSTRAINT "document_category_pkey" PRIMARY KEY ("version_id","domain","file_name","category_name")
);

-- CreateIndex
CREATE UNIQUE INDEX "content_version_version_number_key" ON "content_version"("version_number");

-- AddForeignKey
ALTER TABLE "category" ADD CONSTRAINT "category_version_id_fkey" FOREIGN KEY ("version_id") REFERENCES "content_version"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "category_parent" ADD CONSTRAINT "category_parent_version_id_fkey" FOREIGN KEY ("version_id") REFERENCES "content_version"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "frame" ADD CONSTRAINT "frame_version_id_fkey" FOREIGN KEY ("version_id") REFERENCES "content_version"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "frame_category" ADD CONSTRAINT "frame_category_version_id_fkey" FOREIGN KEY ("version_id") REFERENCES "content_version"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "document" ADD CONSTRAINT "document_version_id_fkey" FOREIGN KEY ("version_id") REFERENCES "content_version"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "document_category" ADD CONSTRAINT "document_category_version_id_fkey" FOREIGN KEY ("version_id") REFERENCES "content_version"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Exactly one active version (hand-written: Prisma cannot express a partial index).
CREATE UNIQUE INDEX "content_version_one_active" ON "content_version"("is_active") WHERE "is_active";
