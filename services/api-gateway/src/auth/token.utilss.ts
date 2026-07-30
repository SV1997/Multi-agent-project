import { randomBytes } from "crypto";
import { createHmac } from 'node:crypto';

export function refreshTokenGenerator(secret:string){
    const raw = randomBytes(64).toString('hex')
    const hashed = createHmac('sha256',secret).update(raw).digest('hex')
    return {raw, hashed}
}

export function hashToken(secret: string, token:string){
    const hashed = createHmac('sha256',secret).update(token).digest('hex')
    return hashed
}