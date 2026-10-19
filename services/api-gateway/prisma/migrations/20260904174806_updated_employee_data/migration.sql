/*
  Warnings:

  - You are about to drop the column `leave` on the `EmployeeData` table. All the data in the column will be lost.
  - You are about to drop the column `userEmail` on the `EmployeeData` table. All the data in the column will be lost.
  - A unique constraint covering the columns `[employee_email]` on the table `EmployeeData` will be added. If there are existing duplicate values, this will fail.
  - Added the required column `employee_email` to the `EmployeeData` table without a default value. This is not possible if the table is not empty.
  - Added the required column `leave_balance` to the `EmployeeData` table without a default value. This is not possible if the table is not empty.
  - Added the required column `leave_type` to the `EmployeeData` table without a default value. This is not possible if the table is not empty.

*/
-- DropForeignKey
ALTER TABLE "EmployeeData" DROP CONSTRAINT "EmployeeData_userEmail_fkey";

-- DropIndex
DROP INDEX "EmployeeData_userEmail_key";

-- AlterTable
ALTER TABLE "EmployeeData" DROP COLUMN "leave",
DROP COLUMN "userEmail",
ADD COLUMN     "employee_email" TEXT NOT NULL,
ADD COLUMN     "leave_balance" INTEGER NOT NULL,
ADD COLUMN     "leave_type" TEXT NOT NULL;

-- CreateIndex
CREATE UNIQUE INDEX "EmployeeData_employee_email_key" ON "EmployeeData"("employee_email");

-- AddForeignKey
ALTER TABLE "EmployeeData" ADD CONSTRAINT "EmployeeData_employee_email_fkey" FOREIGN KEY ("employee_email") REFERENCES "User"("Email") ON DELETE RESTRICT ON UPDATE CASCADE;
