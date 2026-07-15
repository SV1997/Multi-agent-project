import { Body, Controller, UseGuards, Post, Req } from '@nestjs/common';
import {QueryService} from "./query.service";
import { AuthguardGuard } from 'src/guards/auth/authguard/authguard.guard';
import { QueryDTO } from './dto/query.dto';
interface AuthenticatedRequest extends Request{
    user:{sub:number; email:string; role: string};
}
@Controller('query')
export class QueryController {
    constructor(private readonly queryServuce:QueryService){}

    @UseGuards(AuthguardGuard)
    @Post()
    query(@Body() queryDto:QueryDTO, @Req() req:AuthenticatedRequest){
        return this.queryServuce.forwardQuery(queryDto.query, req.user.role)
    }

}
