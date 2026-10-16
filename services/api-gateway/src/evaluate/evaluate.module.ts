import { Module } from '@nestjs/common';
import { EvaluateService } from './evaluate.service';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { HttpModule } from '@nestjs/axios';
import { EvaluateController } from './evaluate.controller';
@Module({
  imports:[HttpModule.registerAsync({
      imports:[ConfigModule],
      inject: [ConfigService],
      useFactory:async(configService:ConfigService)=>({
      timeout:120000,
      maxRedirects:5,
      })
    })],
  providers: [EvaluateService],
  controllers: [EvaluateController]
})
export class EvaluateModule {}
