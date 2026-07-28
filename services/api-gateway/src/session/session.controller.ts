import { Controller, Post, Get, Param, UseGuards, Req } from '@nestjs/common';
import { AuthguardGuard } from 'src/guards/auth/authguard/authguard.guard';
import {type AuthenticatedRequest } from 'src/query/query.controller';
import { SessionService } from './session.service';
import {v4 as uuidv4} from 'uuid';
@Controller('session')
export class SessionController {
constructor(private readonly sessionService:SessionService){}
@UseGuards(AuthguardGuard)
@Post("/create")
async createSession(@Req() req:AuthenticatedRequest){
const thread_id=uuidv4()
const session = await this.sessionService.createSession(req.user.sub, thread_id)
return {sessionId:session.id}
}

@UseGuards(AuthguardGuard)
@Get("/list")
async listSessions(@Req() req:AuthenticatedRequest){
return this.sessionService.listSessions(req.user.sub)
}

@UseGuards(AuthguardGuard)
@Get("/:id/messages")
async getMessages(@Param('id') id:string, @Req() req:AuthenticatedRequest){
return this.sessionService.getMessages(id, req.user.sub)
}

}
