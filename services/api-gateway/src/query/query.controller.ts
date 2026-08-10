import { Body, Controller, Get, Param, UseGuards, Post, Req, Res } from '@nestjs/common';
import {QueryService} from "./query.service";
import { AuthguardGuard } from 'src/guards/auth/authguard/authguard.guard';
import { QueryDTO } from './dto/query.dto';
import type {Response} from  'express'
import { ResumeDto } from './dto/resume.dto';
import { FlagDto } from './dto/flag.dto';
import { RoleguardGuard } from 'src/guards/role/roleguard/roleguard.guard';
import { Roles } from 'src/guards/role/roleguard/role.decorator';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { SessionService } from 'src/session/session.service';
import { MessageRole } from 'generated/prisma/enums';
export interface AuthenticatedRequest extends Request{
    user:{sub:number; email:string; role: string};
}
@Controller('query')
export class QueryController {
    constructor(
      private readonly queryService:QueryService,
      private readonly sessionService:SessionService,
      private readonly eventEmitter:EventEmitter2
    ){}

    @UseGuards(AuthguardGuard)
    @Post()
    query(@Body() queryDto:QueryDTO, @Req() req:AuthenticatedRequest){
        return this.queryService.forwardQuery(queryDto.query, req.user.role)
    }
    @Roles("admin")
    @UseGuards(AuthguardGuard,RoleguardGuard)
    @Post("resume")
    queryResume(@Body() resumeDto:ResumeDto){
        return this.queryService.forwardQueryReume(resumeDto)
    }

    @UseGuards(AuthguardGuard)
    @Post('stream')
    async queryStream(@Body() queryDto:QueryDTO, @Req() req:AuthenticatedRequest, @Res() res:Response){
        this.queryService.isSessionPending(queryDto.sessionId)
        const turnId=queryDto.turnId
        await this.sessionService.recordUserMessage(MessageRole.USER,queryDto.sessionId,queryDto.query,turnId)
        const stream = await this.queryService.forwardQueryStream(queryDto.query,req.user.role, queryDto.sessionId)
        
        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive')
        let buffer = ""
        let answerBuffer = ""
        // Node emits 'data'/'end' without waiting on async listeners, so we
        // chain each chunk's processing and make 'end' await the chain -
        // otherwise res.end() can fire while the paused_for_review frame's
        // DB write (and its res.write) is still in flight, closing the
        // response before that frame ever reaches the client.
        let processing: Promise<void> = Promise.resolve();

        stream.on('data', (chunk: Buffer) => {
            processing = processing.then(async () => {
                buffer += chunk.toString();
                const frames = buffer.split("\n\n")
                buffer = frames.pop()||''
                for (const frame of frames){
                    const line = frame.split('\n').find(l=>l.startsWith("data:"))
                        if (!line) continue;
                        const dataStr = line.slice(5).trim();
                        if (dataStr === '[DONE]'){
                            await this.sessionService.recordUserMessage(MessageRole.ASSISTANT,queryDto.sessionId,answerBuffer,turnId)
                            res.write(`data:${dataStr}\n\n`);

                            continue;
                        }

                        try {
                            const parsed = JSON.parse(dataStr);
                            answerBuffer+=parsed.token!==undefined?parsed.token:""

                            console.log(parsed );

                            if (parsed.status === 'paused_for_review') {
                                await this.queryService.forwardQueryStreamPrismaInitiate(parsed.thread_id,parsed.review_payload,req.user.sub, req.user.role, queryDto.sessionId, turnId)
                                res.write(`data:${JSON.stringify({...parsed, turnId, sessionId: queryDto.sessionId})}\n\n`);

                            }
                            else{
                                res.write(`data:${dataStr}\n\n`)
                            }
                        } 
                        catch {
                            // partial/non-JSON frame, ignore
                        }
                }
            });
        });


    stream.on('end', async () => {
        await processing;
        res.end()
    })
    }
    @Roles("admin")
    @UseGuards(AuthguardGuard, RoleguardGuard)
   @Post('resolve-review')
async resolveReviewEndpoint(@Body() resumeDto: ResumeDto) {
    const stream = await this.queryService.forwardQueryStreamResume(resumeDto)

    let buffer = ""
    let answer = ""
    let pausedAgain = false

    for await (const chunk of stream) {
        buffer += chunk.toString()
        const frames = buffer.split("\n\n")
        buffer = frames.pop() || ''
        for (const frame of frames) {
            const line = frame.split('\n').find(l => l.startsWith("data:"))
            if (!line) continue
            const dataStr = line.slice(5).trim()
            if (dataStr === '[DONE]') continue
            try {
                const parsed = JSON.parse(dataStr)
                if (parsed.status === 'paused_for_review') pausedAgain = true
                else if (typeof parsed.token === 'string') answer += parsed.token
            } catch {}
        }
    }

    if (!pausedAgain) {
        await this.queryService.resolveReview(resumeDto.threadId, answer)
    }

    return { success: true, pausedAgain }
}
    @UseGuards(AuthguardGuard)
    @Post("flag")
    async flagQuery(@Body() flagDto:FlagDto, @Req() req:AuthenticatedRequest){
        return this.queryService.recordFlag(flagDto, req.user.sub)
    }

    @UseGuards(AuthguardGuard,RoleguardGuard)
    @Roles('admin')
    @Get('pending-reviews')
    async getPendingReviews(){
       return this.queryService.getPendingReviews()
    }

    @UseGuards(AuthguardGuard)
    @Get('notifications/:thread_id')
    async waitForResolution(@Param('thread_id') thread_id:string, @Res() res:Response){
        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive')

        const existing = await this.queryService.getReviewByThreadId(thread_id)
        if (existing?.resolved) {
            res.write(`data:${JSON.stringify({status:'resolved', result:{answer: existing.answer}})}\n\n`);
            res.end();
            return
        }

        const listener = (result:any)=>{
            console.log(result,"161");
            
            res.write(`data:${JSON.stringify({status:'resolved', result})}\n\n`);
            res.end();
        }

        this.eventEmitter.once(`review-resolved:${thread_id}`,listener)

        res.on('close',()=>{
            this.eventEmitter.removeListener(`review-resolved:${thread_id}`,listener)
        })
    }
    @UseGuards(AuthguardGuard)
    @Post('my-pending-reviews')
    async getMyPendingReviews(@Body('sessionId') sessionId:string,@Req() req:AuthenticatedRequest){
        return this.queryService.getMyPendingReview(req.user.sub, sessionId)
    }
}
