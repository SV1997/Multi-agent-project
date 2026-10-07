-- CreateTable
CREATE TABLE "LeaveRecord" (
    "id" SERIAL NOT NULL,
    "leave_applied_by" TEXT NOT NULL,
    "start_date" TIMESTAMP(3) NOT NULL,
    "end_date" TIMESTAMP(3) NOT NULL,
    "total_number_of_days" INTEGER NOT NULL,

    CONSTRAINT "LeaveRecord_pkey" PRIMARY KEY ("id")
);

-- AddForeignKey
ALTER TABLE "LeaveRecord" ADD CONSTRAINT "LeaveRecord_leave_applied_by_fkey" FOREIGN KEY ("leave_applied_by") REFERENCES "User"("Email") ON DELETE RESTRICT ON UPDATE CASCADE;
