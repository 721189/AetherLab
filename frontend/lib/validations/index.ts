import { z } from "zod";

// Mirrors backend password rules: >=12 chars, upper, lower, digit, special.
const passwordRegex = /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/;

export const passwordSchema = z
  .string()
  .min(12, "Password must be at least 12 characters long")
  .regex(/[A-Z]/, "Must contain at least one uppercase letter")
  .regex(/[a-z]/, "Must contain at least one lowercase letter")
  .regex(/\d/, "Must contain at least one digit")
  .regex(passwordRegex, "Must contain at least one special character");

export const loginSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});

export const registerSchema = z
  .object({
    email: z.string().min(1, "Email is required").email("Enter a valid email"),
    password: passwordSchema,
    confirmPassword: z.string().min(1, "Please confirm your password"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

export const projectSchema = z.object({
  name: z
    .string()
    .min(1, "Name is required")
    .max(255, "Name must be 255 characters or fewer"),
  description: z
    .string()
    .max(1000, "Description must be 1000 characters or fewer")
    .optional()
    .or(z.literal("")),
});

export const agentSchema = z.object({
  name: z
    .string()
    .min(1, "Name is required")
    .max(255, "Name must be 255 characters or fewer"),
  description: z
    .string()
    .max(1000, "Description must be 1000 characters or fewer")
    .optional()
    .or(z.literal("")),
  model: z.string().min(1, "Model is required").max(100),
  system_prompt: z.string().optional().or(z.literal("")),
  temperature: z.coerce
    .number()
    .min(0, "Temperature must be between 0 and 2")
    .max(2, "Temperature must be between 0 and 2"),
  max_tokens: z.coerce
    .number()
    .min(1, "Max tokens must be at least 1")
    .max(4096, "Max tokens must be 4096 or fewer")
    .optional()
    .nullable(),
  status: z.enum(["active", "inactive", "paused", "archived"]),
  is_public: z.boolean().optional(),
});

export type LoginValues = z.infer<typeof loginSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
export type ProjectValues = z.infer<typeof projectSchema>;
export type AgentValues = z.infer<typeof agentSchema>;
