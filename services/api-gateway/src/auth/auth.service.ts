import { ConflictException, Injectable, UnauthorizedException, InternalServerErrorException } from '@nestjs/common';
import {LoginDto} from "./dto/Login.dto"
import * as bcrypt from 'bcrypt'
import { JwtService } from '@nestjs/jwt';
import { RegisterDto } from './dto/Register.dto';
import { PrismaService } from 'src/prisma/prisma.service';
import { refreshTokenGenerator, hashToken } from './token.utilss';
import { ConfigService } from '@nestjs/config';
import { ExceptionsHandler } from '@nestjs/core/exceptions/exceptions-handler';
@Injectable()
export class AuthService {
    constructor(private jwtService:JwtService, 
        private prismaService:PrismaService,
    private configService:ConfigService){}
    async login(loginData:LoginDto){
        const email = loginData.email
        const password = loginData.password
        const user = await this.prismaService.user.findUnique({
            where:{
                Email:email
            }
        })
        if(!user){
            throw new UnauthorizedException("Invalid Credentials")
        }
        const isMatch = await bcrypt.compare(password,user.password);
        if(!isMatch){
            throw new UnauthorizedException('Invalid crerds')
        }
        const secret= this.configService.get<string>("REFRESH_TOKEN_SECRET")||"";
        const {raw,hashed}=refreshTokenGenerator(secret)
        try {
            await this.prismaService.refreshToken.create({
                data:{token:hashed,
                    userId:user.id,
                    expiresAt:new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
                }
            })
        } catch (error) {
            throw new InternalServerErrorException('Failed to create refresh token')
            
        }
        const token=this.jwtService.sign({
            sub:user.id,
            email:email,
            role:user.role
        })
        return {accessToken:token, refreshToken:raw}
    }

    async register(registerData:RegisterDto){
        const email = registerData.email
        const password = registerData.password
        const name = registerData.name
        const user = await this.prismaService.user.findUnique({
            where:{
                Email:email
            }
        })
        if(user){
            throw new ConflictException("user already present")
        }
        const hashedPassword = await bcrypt.hash(password,10)
        const newUser = await this.prismaService.user.create({
            data:{
                name:name,
                Email:email,
                password:hashedPassword,
                role:'guest'
            }
        })
        
        return {messsage:"User registered successfully", data:{email:email, password: password}, statusCode:200}
        }

    async refreshToken(rawToken:string){
        const secret= this.configService.get<string>("REFRESH_TOKEN_SECRET")||"";
        const hashed1= hashToken(secret, rawToken)

        try {
            const tokenData=await this.prismaService.refreshToken.findUnique({
                where:{
                    token:hashed1
                },
                include:{
                    user:true
                }
            })
            if(!tokenData){
                throw new UnauthorizedException()
            }
            if(Date.now()>tokenData.expiresAt.getTime()){
                throw new UnauthorizedException("token expired")
            }
            if (tokenData.revoked) throw new UnauthorizedException('Token revoked')
            await this.prismaService.refreshToken.update({
                where:{
                    token:hashed1
                },
                data:{
                    revoked:true
                }
            })
            const {raw,hashed}=refreshTokenGenerator(secret)
             await this.prismaService.refreshToken.create({
                data:{token:hashed,
                    userId:tokenData.userId,
                    expiresAt:new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
                }
            })
            const token=this.jwtService.sign({
            sub:tokenData.userId,
            email:tokenData.user.Email,
            role:tokenData.user.role
        })
        return {accessToken:token, refreshToken:raw}
        } catch (error) {
            if (error instanceof UnauthorizedException) throw error
                throw new UnauthorizedException()
        }
    }

    async logout(rawToken:string){
        const secret= this.configService.get<string>("REFRESH_TOKEN_SECRET")||"";
        const hashed1= hashToken(secret, rawToken)
        try {
           await this.prismaService.refreshToken.update({
                where:{
                    token:hashed1
                },
                data:{
                    revoked:true
                }
            })
        } catch (error) {
            throw new InternalServerErrorException()
        }
    }
}
