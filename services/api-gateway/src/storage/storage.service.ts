import { Injectable, InternalServerErrorException, Logger } from '@nestjs/common';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { ConfigService } from '@nestjs/config';
import { S3Client, PutObjectCommand, GetObjectCommand } from '@aws-sdk/client-s3';
@Injectable()
export class StorageService {
    private readonly logger = new Logger(StorageService.name);
    private readonly s3: S3Client;
    private readonly bucket:string;
    constructor(
        private configService:ConfigService){
        this.s3 = new S3Client({
            endpoint: configService.get('SEAWEED_S3_ENDPOINT'),
            region: 'us-east-1',
            forcePathStyle: true,
            credentials: {accessKeyId:'any', secretAccessKey:'any'},

        })
            this.bucket = configService.get('SEAWEED_BUCKET')||"";
    }
    
    async uploadFile(buffer:Buffer, filename:string): Promise<string>{
         const command = new PutObjectCommand({
            Bucket:this.bucket,
            Key:filename,
            Body: buffer
         });
         try {
            await this.s3.send(command)
            return filename
         } catch (error) {
            this.logger.error(error)
            throw new InternalServerErrorException('failed to upload file')
         }
    }

    async getPresignedUrl(key:string): Promise<string>{
        const command = new GetObjectCommand({
            Bucket:this.bucket,
            Key:key,
        });
        try {
            const url = await getSignedUrl(this.s3,command, {expiresIn:3600});
            return url
        } catch (error) {
            throw new InternalServerErrorException('Failed to generate presigned url')            
        }
    } 
}
