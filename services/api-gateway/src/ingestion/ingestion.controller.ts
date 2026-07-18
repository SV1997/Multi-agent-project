import { Controller, Post, Body, UseGuards, Req } from '@nestjs/common';
import {IngestionDto} from "./Dto/Ingestion.dto"
import { AuthguardGuard } from 'src/guards/auth/authguard/authguard.guard';
import { RoleguardGuard } from 'src/guards/role/roleguard/roleguard.guard';
import { Roles } from 'src/guards/role/roleguard/role.decorator';
import type {Request} from  'express'
import { IngestionService } from './ingestion.service';
interface AuthenticatedRequest extends Request{
    user:{sub:number; email:string; role: string};
}
@Controller('ingestion')
export class IngestionController {

    constructor(private readonly ingestionService:IngestionService){}

    @UseGuards(AuthguardGuard)
    @Post()
    ingestion(@Body() ingestionDto:IngestionDto, @Req() req:AuthenticatedRequest){
        return this.ingestionService.ingestion(ingestionDto, req.user.role, req.user.sub)
    }

}
