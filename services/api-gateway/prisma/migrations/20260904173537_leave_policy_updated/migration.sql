-- CreateTable
CREATE TABLE "EmployeeData" (
    "id" SERIAL NOT NULL,
    "userEmail" TEXT NOT NULL,
    "leave" INTEGER NOT NULL,

    CONSTRAINT "EmployeeData_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "EmployeeData_userEmail_key" ON "EmployeeData"("userEmail");

-- AddForeignKey
ALTER TABLE "EmployeeData" ADD CONSTRAINT "EmployeeData_userEmail_fkey" FOREIGN KEY ("userEmail") REFERENCES "User"("Email") ON DELETE RESTRICT ON UPDATE CASCADE;
