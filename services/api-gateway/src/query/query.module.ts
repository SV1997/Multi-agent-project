import { Module } from '@nestjs/common';
import { QueryService } from './query.service';
import { QueryController } from './query.controller';
import { HttpModule } from '@nestjs/axios';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { SessionModule } from '../session/session.module';
@Module({
  imports:[HttpModule.registerAsync({
    imports:[ConfigModule],
    inject:[ConfigService],
    useFactory: async(configService:ConfigService)=>({
    timeout:120000,
    maxRedirects:5,
    })
  }), SessionModule],
  providers: [QueryService],
  controllers: [QueryController]
})
export class QueryModule {}
