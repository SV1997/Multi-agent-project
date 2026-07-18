import { HttpService } from '@nestjs/axios';
import { Injectable, ForbiddenException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { ROLE_NAMESPACE_ACCESS } from 'src/auth/rbac';
import { firstValueFrom, catchError } from 'rxjs';
import { AxiosError } from 'axios';
import { Logger } from '@nestjs/common';
import { InternalServerErrorException } from '@nestjs/common';
import { IngestionDto } from './Dto/Ingestion.dto';
import { PrismaService } from 'src/prisma/prisma.service';

@Injectable()
export class IngestionService {
    private readonly logger = new Logger(IngestionService.name);
    constructor(private httpService: HttpService, private configService: ConfigService, private prismaService: PrismaService) { }

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
            
        return res.data
    }


}
