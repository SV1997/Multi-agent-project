import { HttpService } from '@nestjs/axios';
import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { ROLE_NAMESPACE_ACCESS } from 'src/auth/rbac';
import { firstValueFrom, catchError } from 'rxjs';
import { AxiosError } from 'axios';
import { Logger } from '@nestjs/common';
import { InternalServerErrorException } from '@nestjs/common';
import { ResumeDto } from './dto/resume.dto';
@Injectable()
export class QueryService {
    private readonly logger = new Logger(QueryService.name);
    
    constructor(private httpService:HttpService, private configService:ConfigService){}
    async forwardQuery(query:string, role:string){
      
         const allowedNamespaces = ROLE_NAMESPACE_ACCESS[role] || [];
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
    console.log(res.data["requires_human_review"]);
    
    if (res.data["thread_id"]){
      return {message:" This response required review from admin",status:res.data["status"] ,thread_id:res.data["thread_id"]}
    }
    return res.data
    }

    async forwardQueryReume(resumeDto:ResumeDto){
      const orchestratorUrl = this.configService.get<string>('ORCHESTRATOR_URL')||"";
      const res = await firstValueFrom(this.httpService.post(orchestratorUrl+"/resume",{
        human_response:resumeDto.human_response,
        thread_id:resumeDto.thread_id
      },
    {
      headers:{
        "x-internal-secret": this.configService.get<string>("INTERNAL_SECRET")
      }
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

    async forwardQueryStream(query:string, role:string){
      const allowedNamespaces = ROLE_NAMESPACE_ACCESS[role] || [];
         const orchestratorUrl = this.configService.get<string>('ORCHESTRATOR_URL')||"";
         const res = await firstValueFrom(this.httpService.post(`${orchestratorUrl}/stream`,{
      query: query,
      allowed_namespace: allowedNamespaces,
    },
    {
      headers: {
        'x-internal-secret': this.configService.get<string>('INTERNAL_SECRET'),
      },
      responseType: 'stream'
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

  async forwardQueryStreamResume(resumeDto:ResumeDto){
         const orchestratorUrl = this.configService.get<string>('ORCHESTRATOR_URL')||"";
         const res = await firstValueFrom(this.httpService.post(`${orchestratorUrl}/stream/resume`,{
      human_response:resumeDto.human_response,
        thread_id:resumeDto.thread_id
    },
    {
      headers: {
        'x-internal-secret': this.configService.get<string>('INTERNAL_SECRET'),
      },
      responseType: 'stream'
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
