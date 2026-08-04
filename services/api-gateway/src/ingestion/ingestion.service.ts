import { HttpService } from '@nestjs/axios';
import { Injectable, ForbiddenException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { ROLE_NAMESPACE_ACCESS } from 'src/auth/rbac';
import { firstValueFrom, catchError } from 'rxjs';
import { AxiosError } from 'axios';
import { Logger } from '@nestjs/common';
import { InternalServerErrorException } from '@nestjs/common';
import { IngestionDto, UploadIngestionDto } from './Dto/Ingestion.dto';
import { PrismaService } from 'src/prisma/prisma.service';
import { StorageService } from 'src/storage/storage.service';

@Injectable()
export class IngestionService {
    private readonly logger = new Logger(IngestionService.name);
    constructor(private httpService: HttpService, 
        private configService: ConfigService, 
        private prismaService: PrismaService,
        private storageService: StorageService
    ) { }

    async failedLog(ingestionDto:IngestionDto, sub: number){
        const failedAttemptIngestion = await this.prismaService.ingestionLog.create({
                data: {
                    user_id: sub,
                    namespace: ingestionDto.namespace,
                    sources: ingestionDto.source.map((s)=>{return{
                        path:s.path,
                        type:s.type
                    }}),
                    status:"failed"
                }
                })
    }
    async failedUploadLog(uploadIngestionDto:UploadIngestionDto,key:{path:string, type:string}[] ,sub: number){
        const failedAttemptIngestion = await this.prismaService.ingestionLog.create({
                data: {
                    user_id: sub,
                    namespace: uploadIngestionDto.namespace,
                    sources: key,
                    status:"failed"
                }
                })
    }
    async ingestion(ingestionDto: IngestionDto, role: string, sub: number) {
        const allowednNamespaces = ROLE_NAMESPACE_ACCESS[role] || []
        console.log(role, allowednNamespaces.includes(ingestionDto.namespace));
        
        if (!allowednNamespaces.includes(ingestionDto.namespace)) {
                // await this.failedLog(ingestionDto,sub)
            
            throw new ForbiddenException(
                `you are not allowed to ingest in the ${ingestionDto.namespace} namespace`
            )
        }
        const ingestionUrl = this.configService.get<string>('INGESTION_URL') || "";
        const res = await firstValueFrom(this.httpService.post(ingestionUrl, {
            namespace: ingestionDto.namespace,
            source: ingestionDto.source
        },
            {
                headers: {
                    'x-internal-secret': this.configService.get<string>('INTERNAL_SECRET'),
                }
            }
        ).pipe(
            catchError(async (error: AxiosError) => {
                this.logger.error(error.response?.data)
                await this.failedLog(ingestionDto,sub)
                throw new InternalServerErrorException('An error occurred while contacting the ingestion service');
            }
            )
        ))
                const successAttemptIngestion =await this.prismaService.ingestionLog.create({
                data: {
                    user_id: sub,
                    namespace: ingestionDto.namespace,
                    sources:ingestionDto.source.map((s)=>{return{
                        path:s.path,
                        type:s.type
                    }}),
                    status:"success"
                }
            })
            
        return {data:res.data, success:true}
    }
    async uploadFile(uploadIngestionDto: UploadIngestionDto, files: Express.Multer.File[], role: string, sub: number) {
    const allowedNamespaces = ROLE_NAMESPACE_ACCESS[role] || []
    if (!allowedNamespaces.includes(uploadIngestionDto.namespace)) {
        throw new ForbiddenException(`you are not allowed to ingest in the ${uploadIngestionDto.namespace} namespace`)
    }

    const uploaded = await Promise.all(files.map(async (file) => {
        const fileName = `${crypto.randomUUID()}-${file.originalname}`
        const key = await this.storageService.uploadFile(file.buffer, fileName)
        const url = await this.storageService.getPresignedUrl(key)
        return { key, url, type: uploadIngestionDto.type }
    }))

    const ingestionUrl = this.configService.get<string>('INGESTION_URL') || "";
    const keys = uploaded.map(u => {return{path:u.key, type:u.type}})

    const res = await firstValueFrom(this.httpService.post(ingestionUrl, {
        namespace: uploadIngestionDto.namespace,
        source: uploaded.map(u => ({ path: u.url, type: u.type }))
    }, {
        headers: { 'x-internal-secret': this.configService.get<string>('INTERNAL_SECRET') },
    }).pipe(
        catchError(async (error: AxiosError) => {
            this.logger.error(error.response?.data)
            await this.failedUploadLog(uploadIngestionDto, keys, sub)
            throw new InternalServerErrorException('An error occurred while contacting the ingestion service');
        })
    ))

    await this.prismaService.ingestionLog.create({
        data: { user_id: sub, namespace: uploadIngestionDto.namespace, sources: keys, status: "success" }
    })

    return { data: res.data, success: true }
}


}
