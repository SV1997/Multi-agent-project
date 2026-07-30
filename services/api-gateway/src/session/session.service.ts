import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from 'src/prisma/prisma.service';
import { MessageRole } from 'generated/prisma/enums';

@Injectable()
export class SessionService {
    constructor(private prismaService:PrismaService){}
    async createSession(userId:number, thread_id:string){
        const res = await this.prismaService.session.create({
            data:{
                userId:userId,
                thread_id:thread_id
            }
        })
        return res
    }

    async listSessions(userId:number){
        const sessions = await this.prismaService.session.findMany({
            where:{userId},
            orderBy:{updatedAt:'desc'},
            include:{
                messages:{
                    where:{role:MessageRole.USER},
                    orderBy:{createdAt:'asc'},
                    take:1
                }
            }
        })
        return sessions.map((s)=>({
            id:s.id,
            createdAt:s.created_At,
            updatedAt:s.updatedAt,
            title: s.messages[0]?.content?.slice(0,60) || 'New session'
        }))
    }

    async getMessages(sessionId:string, userId:number){
        const session = await this.prismaService.session.findFirst({where:{id:sessionId, userId}})
        if(!session) throw new NotFoundException('Session not found')

        return this.prismaService.message.findMany({
            where:{sessionId},
            orderBy:{createdAt:'asc'}
        })
    }

    async recordUserMessage(role:MessageRole,sessionId:string, query:string, turnId:string){
        const res = await this.prismaService.message.create({
            data:{
                sessionId:sessionId,
                role: role,
                content:query,
                turnId: turnId
            }
        })
        return res

    }

}
