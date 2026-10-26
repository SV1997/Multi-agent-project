import { Controller, Post, Param, UseGuards } from '@nestjs/common';
import { EvaluateService } from './evaluate.service';
import { AuthguardGuard } from 'src/guards/auth/authguard/authguard.guard';
import { Roles } from 'src/guards/role/roleguard/role.decorator';
import { RoleguardGuard } from 'src/guards/role/roleguard/roleguard.guard';

@Controller('evaluate')
export class EvaluateController {
    constructor(private EvaluateService:EvaluateService, ){}
// @Roles('admin')
// @UseGuards(AuthguardGuard, RoleguardGuard)
@Post(":threadId")
async evaluate(@Param('threadId') threadId:string){
    const res =await this.EvaluateService.evaluate({threadId})
    return {data:res, message:"evaluation done", status: 200}
}

}
