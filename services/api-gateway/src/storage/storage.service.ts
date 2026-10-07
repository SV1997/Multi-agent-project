import { Injectable, InternalServerErrorException, Logger, OnModuleInit } from '@nestjs/common';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { ConfigService } from '@nestjs/config';
import { S3Client, PutObjectCommand, GetObjectCommand, CreateBucketCommand } from '@aws-sdk/client-s3';
@Injectable()
export class StorageService implements OnModuleInit {
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

    async onModuleInit() {
        // SeaweedFS's S3 gateway does not auto-create a bucket on first
        // upload - PutObject into a missing bucket fails with AccessDenied
        // rather than a clearer "no such bucket" error, so ensure it exists
        // once at startup instead of failing every upload until someone
        // creates it manually. Retried with backoff since SeaweedFS may
        // still be starting up when this module initializes (depends_on
        // only orders container start, not the S3 gateway's readiness,
        // and this same race exists under k8s where depends_on has no
        // equivalent at all).
        const maxAttempts = 5;
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                await this.s3.send(new CreateBucketCommand({ Bucket: this.bucket }));
                this.logger.log(`Created bucket '${this.bucket}'.`);
                return;
            } catch (error: any) {
                const code = error?.Code || error?.name;
                if (code === 'BucketAlreadyExists' || code === 'BucketAlreadyOwnedByYou') {
                    return;
                }
                if (attempt === maxAttempts) {
                    this.logger.error(`Failed to ensure bucket '${this.bucket}' exists after ${maxAttempts} attempts.`, error);
                    return;
                }
                await new Promise((resolve) => setTimeout(resolve, attempt * 1000));
            }
        }
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
