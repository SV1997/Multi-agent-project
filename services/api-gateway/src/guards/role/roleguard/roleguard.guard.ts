import { CanActivate, ExecutionContext, ForbiddenException, Injectable, UnauthorizedException } from '@nestjs/common';
import { Observable } from 'rxjs';
import { ROLES_KEY } from './role.decorator';
import { Reflector } from '@nestjs/core';
@Injectable()
export class RoleguardGuard implements CanActivate {
  constructor(private reflector:Reflector,
  ){}
  canActivate(
    context: ExecutionContext,
  ): boolean | Promise<boolean> | Observable<boolean> {
    const requiredRoles = this.reflector.getAllAndOverride<string[]>(
      ROLES_KEY, [
        context.getHandler(),
        context.getClass(),
      ]
    )
    if(!requiredRoles) return true
    const request = context.switchToHttp().getRequest();
    const role = request.user.role;
    if(requiredRoles.includes(role)){
      return true
    }
    else{
      throw new ForbiddenException("This role is not allowed for this route")
    }
  }
}
