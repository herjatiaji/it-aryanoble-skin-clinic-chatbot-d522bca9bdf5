"use client";

import { useLogin } from "@/app/login/hooks/use-login";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { cn, getErrorMessage } from "@/lib/utils";
import { RiErrorWarningLine, RiLoader4Line } from "@remixicon/react";
import { useForm } from "@tanstack/react-form";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { loginSchema, type LoginValues } from "./login-schema";

import { useSearchParams } from "next/navigation";

export function LoginForm({ className, ...props }: React.ComponentProps<"form">) {
	const router = useRouter();
	const searchParams = useSearchParams();
	const [loginError, setLoginError] = useState<string | null>(null);
	const { mutate: login, isPending } = useLogin();

	const form = useForm({
		defaultValues: {
			email: "",
			password: "",
		} as LoginValues,
		validators: {
			onChange: loginSchema,
		},
		onSubmit: async ({ value, formApi }) => {
			setLoginError(null);

			const credentials = new URLSearchParams();
			credentials.append("username", value.email);
			credentials.append("password", value.password);

			// Add a slight artificial delay for better UX
			await new Promise((resolve) => setTimeout(resolve, 800));

			login(credentials, {
				onSuccess: ({ userProfile }) => {
					const fromParam = searchParams.get("from");
					let defaultTarget = "/login";

					// Determine standard home
					if (userProfile.type === "DOCTOR") {
						defaultTarget = "/doctor";
					} else if (userProfile.type === "STAFF") {
						defaultTarget = "/dashboard/knowledge";
					}

					// Check if fromParam is allowed for user
					let target = defaultTarget;
					if (fromParam && fromParam.startsWith("/")) {
						if (fromParam.startsWith("/dashboard") && userProfile.type === "STAFF") {
							target = fromParam;
						} else if (fromParam.startsWith("/doctor") && userProfile.type === "DOCTOR") {
							target = fromParam;
						}
					}

					router.push(target);

					// slight delay to show toast after page transition
					setTimeout(() => {
						toast.success(`Welcome, ${userProfile.name}!`);
					}, 300);
				},
				onError: (err) => {
					setLoginError(getErrorMessage(err, "An error occurred during login. Please try again."));
					formApi.reset();
				},
			});
		},
	});

	return (
		<form
			onSubmit={(e) => {
				e.preventDefault();
				e.stopPropagation();
				void form.handleSubmit();
			}}
			className={cn("flex flex-col gap-6", className)}
			{...props}
		>
			<FieldGroup>
				<div className="flex flex-col items-center gap-2 text-center mb-6">
					<h1 className="text-2xl font-bold">Login to your account</h1>
					<p className="text-sm text-muted-foreground">
						Enter your email below to login to your account
					</p>
				</div>

				{loginError && (
					<div className="flex items-center gap-3 text-sm font-medium text-destructive bg-destructive/10 p-3 rounded-md mb-2">
						<RiErrorWarningLine className="h-5 w-5 shrink-0" />
						<span className="leading-tight">{loginError}</span>
					</div>
				)}

				<form.Field name="email">
					{(field) => {
						const isInvalid = field.state.meta.errors && field.state.meta.errors.length > 0;
						return (
							<Field data-invalid={isInvalid}>
								<FieldLabel htmlFor="email">Email</FieldLabel>
								<Input
									name={field.name}
									id="email"
									type="email"
									placeholder="name@example.com"
									value={field.state.value}
									onChange={(e) => field.handleChange(e.target.value)}
									onBlur={field.handleBlur}
									disabled={isPending}
									aria-invalid={isInvalid}
								/>
								{isInvalid && (
									<FieldError errors={field.state.meta.errors as Array<{ message?: string }>} />
								)}
							</Field>
						);
					}}
				</form.Field>

				<form.Field name="password">
					{(field) => {
						const isInvalid = field.state.meta.errors && field.state.meta.errors.length > 0;
						return (
							<Field data-invalid={isInvalid}>
								<div className="flex items-center">
									<FieldLabel htmlFor="password">Password</FieldLabel>
									<a href="#" className="hidden ml-auto text-sm underline-offset-4 hover:underline">
										Forgot your password?
									</a>
								</div>
								<Input
									name={field.name}
									id="password"
									type="password"
									placeholder="••••••••"
									value={field.state.value}
									onChange={(e) => field.handleChange(e.target.value)}
									onBlur={field.handleBlur}
									disabled={isPending}
									aria-invalid={isInvalid}
								/>
								{isInvalid && (
									<FieldError errors={field.state.meta.errors as Array<{ message?: string }>} />
								)}
							</Field>
						);
					}}
				</form.Field>

				<form.Subscribe selector={(state) => [state.isSubmitting]}>
					{([isSubmitting]) => (
						<Field>
							<Button type="submit" disabled={isPending || isSubmitting}>
								{(isPending || isSubmitting) && (
									<RiLoader4Line className="mr-2 h-4 w-4 animate-spin shrink-0" />
								)}
								{isPending || isSubmitting ? "Logging in..." : "Login"}
							</Button>
						</Field>
					)}
				</form.Subscribe>
			</FieldGroup>
		</form>
	);
}
