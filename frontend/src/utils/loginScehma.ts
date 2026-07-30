import {z} from"zod";

export const LoginSchema=z.object({
    email:z.email("Email Id entered should be valid"),
    password:z.string()
    .min(8,"Password cannot be sshorter than 8 chahcters")
    .regex(/^\S*$/, "Spaces Not allowed")
    .max(24, "Password cannot be larer than 24 character")
})

export type loginFormData=z.infer<typeof LoginSchema>