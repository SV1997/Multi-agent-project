import { Controller, Post,Body,Res, Req, UnauthorizedException } from '@nestjs/common';
import { AuthService } from './auth.service';
import { LoginDto} from './dto/Login.dto';
import {RegisterDto} from "./dto/Register.dto"

import { type Response,type Request } from 'express';
@Controller('auth')
export class AuthController {
    constructor(private authService:AuthService){}
    @Post("login")
    async login(@Body() loginDto:LoginDto, @Res({passthrough:true}) response:Response){
        const res =await this.authService.login(loginDto)
        response.cookie('refresh_token', res.refreshToken,{
            httpOnly: true,
            secure: true,
            sameSite: 'strict',
            maxAge: 7*24*60*60*1000
        })
        return{message:"login successful", accessToken:res.accessToken}
    }
    @Post("register")
    register(@Body() registerDto:RegisterDto){
        return this.authService.register(registerDto)
    }
    @Post("refresh")
    async refresh(@Req() req:Request, @Res({passthrough:true}) response:Response){
        const rawToken = req.cookies['refresh_token']
        if (!rawToken) throw new UnauthorizedException()
        const res=await this.authService.refreshToken(rawToken)
        response.cookie('refresh_token', res.refreshToken,{
            httpOnly: true,
            secure: true,
            sameSite: 'strict',
            maxAge: 7*24*60*60*1000
        })
        return {accessToken:res.accessToken}
    }
    @Post("logout")
    async logout(@Req() req:Request,@Res({passthrough:true}) response:Response){
        const rawToken = req.cookies['refresh_token']
        if (!rawToken) throw new UnauthorizedException()
       await this.authService.logout(rawToken)
        response.clearCookie('refresh_token')
        return {message:"logout successful"}
    }
}
