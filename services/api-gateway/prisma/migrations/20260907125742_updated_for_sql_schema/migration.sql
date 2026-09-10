-- CreateEnum
CREATE TYPE "DeploymentStatus" AS ENUM ('succeeded', 'failed', 'in_progress', 'rolled_back');

-- CreateEnum
CREATE TYPE "ContractStatus" AS ENUM ('active', 'expiring_soon', 'expired', 'under_negotiation');

-- CreateTable
CREATE TABLE "LegalContract" (
    "id" SERIAL NOT NULL,
    "contract_number" TEXT NOT NULL,
    "counterparty" TEXT NOT NULL,
    "managed_by_email" TEXT NOT NULL,
    "status" "ContractStatus" NOT NULL DEFAULT 'active',
    "expiry_date" TIMESTAMP(3),
    "summary" TEXT,
    "created_At" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "LegalContract_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Deployment" (
    "id" SERIAL NOT NULL,
    "deployment_id" TEXT NOT NULL,
    "service_name" TEXT NOT NULL,
    "triggered_by_email" TEXT NOT NULL,
    "status" "DeploymentStatus" NOT NULL,
    "deployed_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Deployment_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "LegalContract_contract_number_key" ON "LegalContract"("contract_number");

-- CreateIndex
CREATE UNIQUE INDEX "Deployment_deployment_id_key" ON "Deployment"("deployment_id");

-- AddForeignKey
ALTER TABLE "LegalContract" ADD CONSTRAINT "LegalContract_managed_by_email_fkey" FOREIGN KEY ("managed_by_email") REFERENCES "User"("Email") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Deployment" ADD CONSTRAINT "Deployment_triggered_by_email_fkey" FOREIGN KEY ("triggered_by_email") REFERENCES "User"("Email") ON DELETE RESTRICT ON UPDATE CASCADE;
