import { ConflictException, Injectable, UnauthorizedException } from '@nestjs/common';
import {LoginDto} from "./dto/Login.dto"
import * as bcrypt from 'bcrypt'
import { JwtService } from '@nestjs/jwt';
import { RegisterDto } from './dto/Register.dto';
import { PrismaService } from 'src/prisma/prisma.service';
@Injectable()
export class AuthService {
    constructor(private jwtService:JwtService, 
        private prismaService:PrismaService){}
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
        const token=this.jwtService.sign({
            sub:user.id,
            email:email,
            role:user.role
        })
        return {message:"login successful", accessToken:token}
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
}
