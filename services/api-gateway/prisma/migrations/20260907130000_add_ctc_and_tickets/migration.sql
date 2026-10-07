/*
  Warnings:

  - Added the required column `ctc` to the `EmployeeData` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "EmployeeData" ADD COLUMN     "ctc" DOUBLE PRECISION NOT NULL DEFAULT 0;

-- CreateTable
CREATE TABLE "TICKETS" (
    "id" SERIAL NOT NULL,
    "ticket_id" TEXT NOT NULL,
    "employee_email" TEXT NOT NULL,
    "pourpose" TEXT NOT NULL,
    "created_At" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "TICKETS_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "TICKETS_ticket_id_key" ON "TICKETS"("ticket_id");

-- AddForeignKey
ALTER TABLE "TICKETS" ADD CONSTRAINT "TICKETS_employee_email_fkey" FOREIGN KEY ("employee_email") REFERENCES "User"("Email") ON DELETE RESTRICT ON UPDATE CASCADE;
