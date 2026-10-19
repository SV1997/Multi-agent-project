import { HttpService } from '@nestjs/axios';
import { Injectable, ForbiddenException, HttpException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { ROLE_NAMESPACE_ACCESS } from 'src/auth/rbac';
import { firstValueFrom, catchError } from 'rxjs';
import { AxiosError } from 'axios';
import { Logger } from '@nestjs/common';
import { InternalServerErrorException } from '@nestjs/common';
import { IngestionDto, UploadIngestionDto } from './Dto/Ingestion.dto';
import { PrismaService } from 'src/prisma/prisma.service';
import { StorageService } from 'src/storage/storage.service';
import { createHash } from 'crypto'
@Injectable()
export class IngestionService {
    private readonly logger = new Logger(IngestionService.name);
    constructor(private httpService: HttpService, 
        private configService: ConfigService, 
        private prismaService: PrismaService,
        private storageService: StorageService
    ) { }

    // 4xx from the ingestion service (e.g. a blank file) is a user-facing message; anything else stays generic.
    private toHttpError(error: AxiosError): Error {
        const status = error.response?.status ?? 500;
        const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
        if (status >= 400 && status < 500 && typeof detail === 'string') {
            return new HttpException(detail, status);
        }
        return new InternalServerErrorException('An error occurred while contacting the ingestion service');
    }

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
                throw this.toHttpError(error);
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
    const docIdFor = (namespace: string, originalName: string) =>
    createHash('sha1').update(`${namespace}/${originalName.trim().toLowerCase()}`).digest('hex').slice(0, 16)
    const uploaded = await Promise.all(files.map(async (file) => {
        const fileName = `${crypto.randomUUID()}-${file.originalname}`
        const key = await this.storageService.uploadFile(file.buffer, fileName)
        const url = await this.storageService.getPresignedUrl(key)
        return { key, url, type: uploadIngestionDto.type, doc_id: docIdFor(uploadIngestionDto.namespace, file.originalname) }
    }))

    const ingestionUrl = this.configService.get<string>('INGESTION_URL') || "";
    const keys = uploaded.map(u => {return{path:u.key, type:u.type}})
    const res = await firstValueFrom(this.httpService.post(ingestionUrl, {
        namespace: uploadIngestionDto.namespace,
        source: uploaded.map(u => ({ path: u.url, type: u.type, doc_id: u.doc_id }))
    }, {
        headers: { 'x-internal-secret': this.configService.get<string>('INTERNAL_SECRET') },
    }).pipe(
        catchError(async (error: AxiosError) => {
            this.logger.error(error.response?.data)
            await this.failedUploadLog(uploadIngestionDto, keys, sub)
            throw this.toHttpError(error);
        })
    ))

    await this.prismaService.ingestionLog.create({
        data: { user_id: sub, namespace: uploadIngestionDto.namespace, sources: keys, status: "success" }
    })

    return { data: res.data, success: true }
}


}
