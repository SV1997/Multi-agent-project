import sys
import os
import asyncpg
from ..core.config import DATABASE_URL
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.contracts.schema import SQLRetrievalRequest

async def get_connection():
    return await asyncpg.connect(DATABASE_URL)


async def leave_balance(req: SQLRetrievalRequest):
    conn = await get_connection()
    try:
        row=await conn.fetchrow(
            'SELECT * FROM "EmployeeData" WHERE employee_email = $1',
            req.employee_email,
        )
        if row is None:
                    return [{"source": "sql:leave_balance", "content": "No leave balance record was found for this employee."}]
        return[{"source": "sql:leave_balance", "content": f"{row['employee_email']} has {row['leave_balance']} {row['leave_type']} days remaining."}]
        
    finally:
        await conn.close()

async def CTC_data(req:SQLRetrievalRequest):
      conn = await get_connection()
      try:
            row = await conn.fetchrow(
                  'SELECT CTC FROM "EmployeeData" WHERE employee_email = $1 ',
                  req.employee_email
            )
            if row is None:
                  return [{"source":"sql:CTC_data", "content":"No ctc data available for employee"}]
            return [{"source":"sql:CTC_data", "content":f"{row["employee_email"]} has {row['ctc']}"}]
      finally:
              await conn.close()

async def get_ticket_status(req:SQLRetrievalRequest):
      conn = await get_connection()
      try:
            row = await conn.fetchrow(
                  'SELECT * FROM "TICKETS" WHERE employee_email = $1 ORDER BY "created_At" DESC LIMIT 1',
                  req.employee_email
            )
            print(row, f"Latest ticket {row['ticket_id']} for {row['employee_email']}")
            if row is None:
                  return [{"source":"sql:ticket_status", "content":"No ticket is available for employee"}]
            return [{
                  "source": "sql:ticket_status",
                  "content": (
                        f"Latest ticket {row['ticket_id']} for {row['employee_email']} "
                        f"is {row['status']}. Purpose: {row['pourpose']}"
                  ),
            }]
      finally:
              await conn.close()


async def contract_tracking(req:SQLRetrievalRequest):
      conn = await get_connection()
      try:
            contract_number = req.data.get("contract_number")
            if contract_number is None:
                  return[{"source":"sql:contract_tracking", "content":"Please provide a contract ID"}]
            else:
                  row = await conn.fetchrow(
                        'SELECT * FROM "LegalContract" WHERE contract_number = $1',
                        contract_number
                        
                  )
                  if row is None:
                        return [{"source":"sql:contract_tracking", "content":"No contract_tracking is available for this contract id"}]
                  return [{"source":"sql:contract_tracking", "content":f"{row['contract_number']} status is {row['status']}"}]
      finally:
                    await conn.close()



async def deployment_status(req:SQLRetrievalRequest):
      conn = await get_connection()
      try:
                  row = await conn.fetchrow(
                        'SELECT * FROM "Deployment" WHERE triggered_by_email = $1',
                        req.employee_email
                  )
                  if row is None:
                        return [{"source":"sql:deployment_status", "content":"No deployment status is available for you"}]
                  return [{"source":"sql:deployment_status", "content":f"{row["service_name"]} status is {row["status"]} deployed at {[row["deployed_at"]]}"}]
      finally:
                    await conn.close()
