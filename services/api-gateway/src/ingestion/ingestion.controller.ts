import { Controller, Post, Body, UseGuards, Req, UseInterceptors, UploadedFiles } from '@nestjs/common';
import {IngestionDto, UploadIngestionDto} from "./Dto/Ingestion.dto"
import { AuthguardGuard } from 'src/guards/auth/authguard/authguard.guard';
import { RoleguardGuard } from 'src/guards/role/roleguard/roleguard.guard';
import { Roles } from 'src/guards/role/roleguard/role.decorator';
import type {Request} from  'express'
import { IngestionService } from './ingestion.service';
import { FilesInterceptor } from '@nestjs/platform-express';
import {memoryStorage} from 'multer'
interface AuthenticatedRequest extends Request{
    user:{sub:number; email:string; role: string};
}
@Controller('ingestion')
export class IngestionController {

    constructor(private readonly ingestionService:IngestionService
    ){}
    
    @UseGuards(AuthguardGuard)
    @Post()
    ingestion(@Body() ingestionDto:IngestionDto, @Req() req:AuthenticatedRequest){
        return this.ingestionService.ingestion(ingestionDto, req.user.role, req.user.sub)
    }
    @Post('upload')
    @UseGuards(AuthguardGuard)
    @UseInterceptors(FilesInterceptor('file',10,{
        storage: memoryStorage(),
        limits: {fileSize: 10*1024*1024}
    }))
    uploadFile(@Body() uploadIngestionDto:UploadIngestionDto ,@UploadedFiles() file:Express.Multer.File[],@Req() req:AuthenticatedRequest){
        return this.ingestionService.uploadFile(uploadIngestionDto,file,req.user.role, req.user.sub)
    }


}
