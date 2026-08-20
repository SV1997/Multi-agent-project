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
import { SessionService } from 'src/session/session.service';
import { MessageRole } from 'generated/prisma/enums';
import { NotFoundException } from '@nestjs/common';
@Injectable()
export class QueryService {
    private readonly logger = new Logger(QueryService.name);

    constructor(private httpService:HttpService,
      private configService:ConfigService,
      private prismaService: PrismaService,
      private eventEmitter:EventEmitter2,
     private sessionService:SessionService){}
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
    
    if (res.data["threadId"]){
      return {message:" This response required review from admin",status:res.data["status"] ,threadId:res.data["threadId"]}
    }
    return res.data
    }

    async forwardQueryReume(resumeDto:ResumeDto){
      const orchestratorUrl = this.configService.get<string>('ORCHESTRATOR_URL')||"";
      const res = await firstValueFrom(this.httpService.post(orchestratorUrl+"/resume",{
        human_response:resumeDto.human_response,
        threadId:resumeDto.threadId
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
    await this.resolveReview(resumeDto.threadId, res.data.answer, res.data)

    return res.data
    }

    async resolveReview(threadId:string, answer:string, result:any = { answer }){
      const updatePending = await this.prismaService.pendingReview.update({
        where:{threadId},
        data:{resolved:true, resolvedAt:new Date(), answer}
      })

      this.eventEmitter.emit(`review-resolved:${threadId}`, result)
      const updateMessage = await this.sessionService.updateUserMessage(updatePending.answer, updatePending.turnId || "", updatePending.sessionId)
      console.log(updatePending, updateMessage)
    }

    async forwardQueryStream(query:string, role:string, sessionId:string){
      const allowedNamespaces = ROLE_NAMESPACE_ACCESS[role] || [];

      const session = await this.prismaService.session.findUnique({
        where:{id:sessionId}
      })
      const threadId= session?.thread_id
      if(!threadId){
        throw new NotFoundException(`Session ${sessionId} not found`)
      }
         const orchestratorUrl = this.configService.get<string>('ORCHESTRATOR_URL')||"";
         const res = await firstValueFrom(this.httpService.post(`${orchestratorUrl}/stream`,{
      query: query,
      allowed_namespace: allowedNamespaces,
      thread_id:threadId
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
         console.log(resumeDto);
         
         const res = await firstValueFrom(this.httpService.post(`${orchestratorUrl}/stream/resume`,{
      human_response:resumeDto.human_response,
        thread_id:resumeDto.threadId
    },
    {
      headers: {
        'x-internal-secret': this.configService.get<string>('INTERNAL_SECRET'),
      },
      responseType: 'stream' 
    }).pipe(
            catchError((error:AxiosError)=>{
                // this.logger.error(error.response?.data)
                throw new InternalServerErrorException('An error occurred while contacting the orchestrator');
            }
         )
        ),
    )
    return res.data
    }

    async forwardQueryStreamPrismaInitiate(threadId:string,reviewPayload:any,userId: number, domain:string, sessionId: string, turnId:string){
     
      try {
        const review = await this.prismaService.pendingReview.upsert({
          where:{threadId},
          create:{
            threadId: threadId,
            sessionId:sessionId,
            domain: domain,
            turnId:turnId,
            userId: userId,
            sources: reviewPayload.answer.sources.map((s:any)=>JSON.stringify(s)),
            context: reviewPayload.context.map((c:any)=>JSON.stringify(c)),
            answer: reviewPayload.answer.answer,
            confidence: reviewPayload.answer.confidence,
            resolved: false
          },
          update:{
            sessionId:sessionId,
            domain: domain,
            turnId:turnId,
            userId: userId,
            sources: reviewPayload.answer.sources.map(s=>JSON.stringify(s)),
            context: reviewPayload.context.map(c=>JSON.stringify(c)),
            answer: reviewPayload.answer.answer,
            confidence: reviewPayload.answer.confidence,
            resolved: false,
            resolvedAt: null
          }
        })
        
        console.log(review);
       await this.sessionService.recordUserMessage(MessageRole.ASSISTANT, sessionId, "__pending_review__",turnId)
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

    async isSessionPending(sessionId:string){
      const session = await this.prismaService.session.findUnique({ where: { id: sessionId } })
      if (!session) throw new NotFoundException("can't send a follo up message for paused session")
    }

    async getPendingReviews(){
      const pr = await this.prismaService.pendingReview.findMany({
        where:{resolved: false },
        orderBy:{createdAt: 'desc'}
      })
      console.log(pr);
      return pr
    }

    async getReviewByThreadId(threadId:string){
      return this.prismaService.pendingReview.findUnique({where:{threadId}})
    }

     async getMyPendingReview(userId:Number, sessionId:string){
      const pr = await this.prismaService.pendingReview.findMany({
        where:{userId: Number(userId), sessionId:sessionId}
      })
      console.log(pr);
      return pr
    }

}
