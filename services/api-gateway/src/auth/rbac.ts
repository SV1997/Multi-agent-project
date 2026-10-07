export const ROLE_NAMESPACE_ACCESS: Record<string,string[]> = {
    legal_team: ['legal'],
    hr_team: ['hr'],
    engineering_team: ['engineering'],
    support_team: ['support'],
    finance_team: ['finance'],
    guest: [],
    admin: ['legal','hr','engineering','finance','support'],
    superadmin: ['legal','hr','engineering','finance','support']
}