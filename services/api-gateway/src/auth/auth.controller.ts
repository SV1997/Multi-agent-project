import { Controller, Post,Body, UseGuards, Get } from '@nestjs/common';
import { AuthService } from './auth.service';
import { LoginDto} from './dto/Login.dto';
import {RegisterDto} from "./dto/Register.dto"
import { Roles } from 'src/guards/role/roleguard/role.decorator';
import { AuthguardGuard } from 'src/guards/auth/authguard/authguard.guard';
import { RoleguardGuard } from 'src/guards/role/roleguard/roleguard.guard';
@Controller('auth')
export class AuthController {
    constructor(private authService:AuthService){}
    @Post("login")
    login(@Body() loginDto:LoginDto){
        return this.authService.login(loginDto)
    }
    @Post("register")
    register(@Body() registerDto:RegisterDto){
        return this.authService.register(registerDto)
    }

}
