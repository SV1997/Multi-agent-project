import { z } from "zod";

export const SignUpSchema = z
  .object({
    name: z.string().min(2, "Name must be at least 2 characters"),
    email: z.email("Email Id entered should be valid"),
    password: z
      .string()
      .min(8, "Password cannot be shorter than 8 characters")
      .regex(/^\S*$/, "Spaces Not allowed")
      .max(24, "Password cannot be larger than 24 characters"),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

export type signUpFormData = z.infer<typeof SignUpSchema>;
