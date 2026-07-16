import { Body, Controller, UseGuards, Post, Req, Res } from '@nestjs/common';
import {QueryService} from "./query.service";
import { AuthguardGuard } from 'src/guards/auth/authguard/authguard.guard';
import { QueryDTO } from './dto/query.dto';
import type {Response} from  'express'
import { ResumeDto } from './dto/resume.dto';
import { RoleguardGuard } from 'src/guards/role/roleguard/roleguard.guard';
import { Roles } from 'src/guards/role/roleguard/role.decorator';
interface AuthenticatedRequest extends Request{
    user:{sub:number; email:string; role: string};
}
@Controller('query')
export class QueryController {
    constructor(private readonly queryService:QueryService){}

    @UseGuards(AuthguardGuard)
    @Post()
    query(@Body() queryDto:QueryDTO, @Req() req:AuthenticatedRequest){
        return this.queryService.forwardQuery(queryDto.query, req.user.role)
    }
    // @Roles("admin")
    // @UseGuards(AuthguardGuard,RoleguardGuard)
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

        stream.pipe(res)
    }

}
