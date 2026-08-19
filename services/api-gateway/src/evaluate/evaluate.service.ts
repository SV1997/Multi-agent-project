import { Injectable, NotFoundException } from '@nestjs/common';
import {evalDto} from "./dto/evaluateDto"
import { ConfigService } from '@nestjs/config';
import { firstValueFrom } from 'rxjs';
import { HttpService } from '@nestjs/axios';
import { PrismaService } from 'src/prisma/prisma.service';
import { MessageRole } from 'generated/prisma/enums';

@Injectable()
export class EvaluateService {
constructor(private ConfigService:ConfigService,
    private httpService:HttpService,
    private prismaervice:PrismaService){}
    async evaluate(evalDto:evalDto){
        const pr = await this.prismaervice.pendingReview.findUnique({where:{threadId: evalDto.threadId}})
        if(!pr) throw new NotFoundException(`pending review for thread ${evalDto.threadId} not found`)

        const userMessage = await this.prismaervice.message.findFirst({
            where:{sessionId: pr.sessionId, turnId: pr.turnId ?? undefined, role: MessageRole.USER}
        })

        const retrieved_context = pr.context

        const evalUrl = this.ConfigService.get<string>('EVALUATION_SERVICE_URL')
        const res = await firstValueFrom(
            this.httpService.post(`${evalUrl}`,{
                query: userMessage?.content ?? '',
                answer: pr.answer,
                confidence: pr.confidence,
                retrieved_context
            },{
                headers:{
                    'x-internal-secret': this.ConfigService.get<string>('INTERNAL_SECRET')
                },
                // Keep this below the browser timeout so the client receives a
                // proper gateway error instead of terminating the request itself.
                timeout: 4 * 60 * 1000,
            })
        )
        const dbRes =await this.prismaervice.pendingReview.update({
            where:{threadId:evalDto.threadId},
            data:{
                faithfulnescore:res.data.faithfulness,
                answerRelevancyScore:res.data.answer_relevancy,
                Flagged:res.data.flagged,
                evaluatedAt: new Date()
            }
        })

        return dbRes
    }
}
