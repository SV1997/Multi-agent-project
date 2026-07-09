from langchain_core.tools import tool

@tool
def check_service_status(service_name:str)-> str:
    """
    This tool should be called only when the infrmation
    about a service need to be retrieved. Information could be 
    health of the service, status of service deployment status.

    Don't call this service when the user as to deploy the service you can't entertain requests like:
    1. Stop the service
    2. redeploy the service
    3. scale the service.

    for the above queries you must flag the query for human review
    """

    return f"Your service with name {service_name} status is good"
