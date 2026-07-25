import { Body, Controller, UseGuards, Post, Req, Res, Get, Param } from '@nestjs/common';
import {QueryService} from "./query.service";
import { AuthguardGuard } from 'src/guards/auth/authguard/authguard.guard';
import { QueryDTO } from './dto/query.dto';
import type {Response} from  'express'
import { ResumeDto } from './dto/resume.dto';
import { FlagDto } from './dto/flag.dto';
import { RoleguardGuard } from 'src/guards/role/roleguard/roleguard.guard';
import { Roles } from 'src/guards/role/roleguard/role.decorator';
import { EventEmitter2 } from '@nestjs/event-emitter';

interface AuthenticatedRequest extends Request{
    user:{sub:number; email:string; role: string};
}
@Controller('query')
export class QueryController {
    constructor(private readonly queryService:QueryService,
        private eventEmitter:EventEmitter2
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
        const stream = await this.queryService.forwardQueryStream(queryDto.query, req.user.role)

        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive')
        let buffer = ""
         stream.on('data', (chunk: Buffer) => {
        buffer += chunk.toString();
        const frames = buffer.split("\n\n")
        buffer = frames.pop()||''
        for (const frame of frames){
            const line = frame.split('\n').find(l=>l.startsWith("data:"))
                if (!line) continue;
                const dataStr = line.slice(5).trim();
                if (dataStr === '[DONE]') continue;

                try {
                    const parsed = JSON.parse(dataStr);
                    console.log(parsed);
                    
                    if (parsed.status === 'paused_for_review') {
                        this.queryService.forwardQueryStreamPrismaInitiate(parsed.thread_id,parsed.review_payload,req.user.sub)
                    }
                } catch {
                    // partial/non-JSON frame, ignore
                }
        }
       
        
        res.write(chunk);
    });

        
    stream.on('end', () => res.end())
    }
    @UseGuards(AuthguardGuard)
    @Post('stream/resume')
    async queryStreamResume(@Body() resumeDto:ResumeDto, @Res() res:Response){
        const stream = await this.queryService.forwardQueryStreamResume(resumeDto)

        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive')

        let buffer = ""
        let answer = ""
        let pausedAgain = false
        stream.on('data', (chunk: Buffer) => {
            buffer += chunk.toString();
            const frames = buffer.split("\n\n")
            buffer = frames.pop() || ''
            for (const frame of frames) {
                const line = frame.split('\n').find(l => l.startsWith("data:"))
                if (!line) continue;
                const dataStr = line.slice(5).trim();
                if (dataStr === '[DONE]') continue;

                try {
                    const parsed = JSON.parse(dataStr);
                    if (parsed.status === 'paused_for_review') {
                        pausedAgain = true
                    } else if (typeof parsed.token === 'string') {
                        answer += parsed.token
                    }
                } catch {
                    // partial/non-JSON frame, ignore
                }
            }

            res.write(chunk);
        });

        stream.on('end', async () => {
            if (!pausedAgain) {
                await this.queryService.resolveReview(resumeDto.thread_id, answer)
            }
            res.end()
        })
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

        const listener = (result:any)=>{
            res.write(`data:${JSON.stringify({status:'resolved', result})}\n\n`);
            res.end();
        }

        this.eventEmitter.once(`review-resolved:${thread_id}`,listener)

        res.on('close',()=>{
            this.eventEmitter.removeListener(`review-resolved:${thread_id}`,listener)
        })
    }
}
