import { Type } from "class-transformer";
import { IsString, IsBoolean ,ValidateNested } from "class-validator";

class humanResponse{
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
    @Type(()=>humanResponse)
    human_response!: humanResponse
}