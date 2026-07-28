import { Type } from "class-transformer";
import { IsString, IsBoolean ,ValidateNested } from "class-validator";

class humanRsponse{
    @IsString()
    revised_answer!: string
    
    @IsBoolean()
    approved!: boolean

    @IsBoolean()
    edited!:boolean
}

export class ResumeDto{
    @IsString()
    threadId!: string;

    @ValidateNested()
    @Type(()=>humanRsponse)
    human_response!: humanRsponse
}