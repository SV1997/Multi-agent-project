import { Module } from '@nestjs/common';
import { IngestionService } from './ingestion.service';
import { IngestionController } from './ingestion.controller';
import { HttpModule } from '@nestjs/axios';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { StorageModule } from 'src/storage/storage.module';
@Module({
  imports:[HttpModule.registerAsync({
    imports:[ConfigModule],
    inject: [ConfigService],
    useFactory:async(configService:ConfigService)=>({
    timeout:120000,
    maxRedirects:5,
    })
  }),StorageModule],
  providers: [IngestionService],
  controllers: [IngestionController]
})
export class IngestionModule {}
