export const ROLE_NAMESPACE_ACCESS: Record<string,string[]>={
    legal_team:['legal'],
    hr_team:['hr'],
    engineering_team:['engineering','coding'],
    support_team: ['support'],
    guest:['hr','engineering','coding','support','legal'],
    admin:['legal','hr','engineering','coding','support']
}