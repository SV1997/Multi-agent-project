import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import { Observable } from 'rxjs';
import { JwtService } from '@nestjs/jwt';
import { TokenExpiredError } from 'jsonwebtoken';
@Injectable()
export class AuthguardGuard implements CanActivate {
  constructor(private jwtService: JwtService) { }
  canActivate(
    context: ExecutionContext,
  ): boolean | Promise<boolean> | Observable<boolean> {
    const request = context.switchToHttp().getRequest();
    const queryToken = request.query.token
    const header = request.headers["authorization"]
    if (!header && !queryToken) {
      throw new UnauthorizedException('No token available')
    }
    try {
      const token = header?header.split(" ")[1]:queryToken;
      console.log(token)
      const payload = this.jwtService.verify(token);
      console.log(payload);
      
      request.user = payload;
      return true
    }
    catch(error) {
      if(error instanceof TokenExpiredError){
        throw new UnauthorizedException("Token has expired")
      }
      throw new UnauthorizedException("invalid token")
    }
  }
}
