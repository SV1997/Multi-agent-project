import { Module } from '@nestjs/common';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { PrismaModule } from './prisma/prisma.module';
import { AuthModule } from './auth/auth.module';
import { ConfigModule } from '@nestjs/config';
import { QueryModule } from './query/query.module';
import { IngestionModule } from './ingestion/ingestion.module';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { SessionModule } from './session/session.module';
import { StorageModule } from './storage/storage.module';
@Module({
  imports:[EventEmitterModule.forRoot(),PrismaModule, AuthModule, ConfigModule.forRoot(
    {
      isGlobal: true
    }
  ), QueryModule, IngestionModule, SessionModule, StorageModule],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
