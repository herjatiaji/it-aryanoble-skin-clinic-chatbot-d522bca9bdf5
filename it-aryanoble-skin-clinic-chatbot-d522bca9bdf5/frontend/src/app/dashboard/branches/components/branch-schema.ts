import { z } from "zod";

export const editTokenSchema = z.object({
	token_limit: z.union([
		z.number().min(0),
		z
			.string()
			.refine((val) => val === "" || !isNaN(parseInt(val.replace(/[^0-9]/g, ""), 10)), {
				message: "Token limit must be a valid number",
			})
			.transform((val) => (val === "" ? 0 : parseInt(val.replace(/[^0-9]/g, ""), 10))),
	]),
});

export type EditTokenValues = z.infer<typeof editTokenSchema>;
