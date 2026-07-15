import { Module } from '@nestjs/common';
import { AuthService } from './auth.service';
import { AuthController } from './auth.controller';
import { JwtModule } from '@nestjs/jwt';
import { ConfigModule, ConfigService } from '@nestjs/config';

@Module({
  imports:[
    JwtModule.registerAsync({
      global:true,
      imports:[ConfigModule],
      inject:[ConfigService],
      useFactory:(configService:ConfigService)=>({
        secret:configService.get<string>('JWT_TOKEN'),
        signOptions:{expiresIn:'1h'}
      }
    ),
    })
  ],
  providers: [AuthService],
  controllers: [AuthController]
})
export class AuthModule {}
