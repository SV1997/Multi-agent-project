-- CreateTable
CREATE TABLE "TicketReview" (
    "id" SERIAL NOT NULL,
    "reason" TEXT NOT NULL,
    "reviewedByUser" TEXT NOT NULL,
    "ticketId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "TicketReview_pkey" PRIMARY KEY ("id")
);

-- AddForeignKey
ALTER TABLE "TicketReview" ADD CONSTRAINT "TicketReview_reviewedByUser_fkey" FOREIGN KEY ("reviewedByUser") REFERENCES "User"("Email") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TicketReview" ADD CONSTRAINT "TicketReview_ticketId_fkey" FOREIGN KEY ("ticketId") REFERENCES "TICKETS"("ticket_id") ON DELETE RESTRICT ON UPDATE CASCADE;
