import { HttpService } from '@nestjs/axios';
import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { ROLE_NAMESPACE_ACCESS } from 'src/auth/rbac';
import { firstValueFrom, catchError } from 'rxjs';
import { AxiosError } from 'axios';
import { Logger } from '@nestjs/common';
import { InternalServerErrorException } from '@nestjs/common';
import { ResumeDto } from './dto/resume.dto';
import { PrismaService } from 'src/prisma/prisma.service';
import { FlagDto } from './dto/flag.dto';
import { EventEmitter2 } from '@nestjs/event-emitter';
@Injectable()
export class QueryService {
    private readonly logger = new Logger(QueryService.name);
    
    constructor(private httpService:HttpService, 
      private configService:ConfigService, 
      private prismaService: PrismaService,
      private eventEmitter:EventEmitter2){}
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
              console.log(error);
              
                this.logger.error(error.response?.data)
                throw new InternalServerErrorException('An error occurred while contacting the orchestrator');
            }
         )
        ),
    )
    await this.resolveReview(resumeDto.thread_id, res.data.answer, res.data)

    return res.data
    }

    async resolveReview(thread_id:string, answer:string, result:any = { answer }){
      const update = await this.prismaService.pendingReview.update({
        where:{thread_id},
        data:{resolved:true, resolvedAt:new Date(), answer}
      })

      this.eventEmitter.emit(`review-resolved:${thread_id}`, result)
      console.log(update)
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

    async forwardQueryStreamPrismaInitiate(thread_id:string,reviewPayload:any,userId: number){
      try {
        const review = await this.prismaService.pendingReview.create({
          data:{
            thread_id: thread_id,
            userId: userId,
            sources: reviewPayload.answer.sources.map(s=>JSON.stringify(s)),
            answer: reviewPayload.answer.answer,
            confidence: reviewPayload.answer.confidence,
            resolved: false
          }
        })
        console.log(review);
        
        return review
      } catch (error) {
        this.logger.error(error)
        throw new Error("something wrong with pending review initiation" + error)
      }
    }

    async recordFlag(flagDto:FlagDto, flaggedByUserId:number){
      try {
        const flag=await this.prismaService.flaggedAnswer.create({
          data:{
            flaggedByUserId:flaggedByUserId,
            domain         : flagDto.domain,
            answer:flagDto.answer,
            Sources: flagDto.source.map(s => ({ path: s.path, type: s.type })),
            reason: flagDto.reason||null
          }
        })

        return flag
      } catch (error) {
        throw new Error("something wrong with query flag" +error)
      }
    }

    async getPendingReviews(){
      const pr = this.prismaService.pendingReview.findMany({
        where:{resolved: false},
        orderBy:{created_At: 'desc'}
      })
      console.log(pr);
      return pr
    }
}
