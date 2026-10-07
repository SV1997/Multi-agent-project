-- CreateTable
CREATE TABLE "ContractReview" (
    "id" SERIAL NOT NULL,
    "reason" TEXT NOT NULL,
    "reviewedByUser" TEXT NOT NULL,
    "contract" TEXT NOT NULL,

    CONSTRAINT "ContractReview_pkey" PRIMARY KEY ("id")
);

-- AddForeignKey
ALTER TABLE "ContractReview" ADD CONSTRAINT "ContractReview_reviewedByUser_fkey" FOREIGN KEY ("reviewedByUser") REFERENCES "User"("Email") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ContractReview" ADD CONSTRAINT "ContractReview_contract_fkey" FOREIGN KEY ("contract") REFERENCES "LegalContract"("contract_number") ON DELETE RESTRICT ON UPDATE CASCADE;
