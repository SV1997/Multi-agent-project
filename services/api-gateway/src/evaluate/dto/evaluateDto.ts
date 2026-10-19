import { IsString } from "class-validator";

export class evalDto{
    @IsString()
    threadId!: string;
}
