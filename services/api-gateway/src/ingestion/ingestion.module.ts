import { Module } from '@nestjs/common';
import { IngestionService } from './ingestion.service';
import { IngestionController } from './ingestion.controller';
import { HttpModule } from '@nestjs/axios';
import { ConfigModule, ConfigService } from '@nestjs/config';
@Module({
  imports:[HttpModule.registerAsync({
    imports:[ConfigModule],
    inject: [ConfigService],
    useFactory:async(configService:ConfigService)=>({
    timeout:120000,
    maxRedirects:5,
    })
  })],
  providers: [IngestionService],
  controllers: [IngestionController]
})
export class IngestionModule {}
