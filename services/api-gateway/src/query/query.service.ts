import { HttpService } from '@nestjs/axios';
import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { ROLE_NAMESPACE_ACCESS } from 'src/auth/rbac';
import { firstValueFrom, catchError } from 'rxjs';
import { AxiosError } from 'axios';
import { Logger } from '@nestjs/common';
import { InternalServerErrorException } from '@nestjs/common';
@Injectable()
export class QueryService {
    private readonly logger = new Logger(QueryService.name);

    constructor(private httpService:HttpService, private configService:ConfigService){}

    async forwardQuery(query:string, role:string){
      
         const allowedNamespaces = ROLE_NAMESPACE_ACCESS[role] || [];
               console.log(allowedNamespaces);
         const orchestratorUrl = this.configService.get<string>('ORCHESTRATOR_URL')||"";
         const res = await firstValueFrom(this.httpService.post(`${orchestratorUrl}`,{
      query: query,
      allowed_namespace: allowedNamespaces,
    },
    {
      headers: {
        'x-internal-secret': this.configService.get<string>('INTERNAL_SECRET'),
      },
    }).pipe(
            catchError((error:AxiosError)=>{
                this.logger.error(error.response?.data)
                throw new InternalServerErrorException('An error occurred while contacting the orchestrator');
            }
         )
        ),
    )
    return res.data
    }
}
