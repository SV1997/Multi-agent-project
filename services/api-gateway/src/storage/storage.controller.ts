import { Controller } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import {memoryStorage} from 'multer'
import {UseInterceptors, UploadedFile, Post } from '@nestjs/common';

@Controller('storage')
export class StorageController {
    
}
