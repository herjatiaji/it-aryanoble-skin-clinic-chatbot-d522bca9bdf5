"use client";

import { useLoginForm } from "@/app/login/hooks/use-login-form";
import { Button } from "@/components/ui/button";
import {
	Field,
	FieldContent,
	FieldError,
	FieldGroup,
	FieldLabel,
	FieldTitle,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { RiEyeLine, RiEyeOffLine, RiLoader4Line } from "@remixicon/react";
import { LoginAlerts } from "./login-alerts";
import { LoginHeader } from "./login-header";

export function LoginForm({ className, ...props }: React.ComponentProps<"form">) {
	const { form, loginError, reasonMessage, showPassword, toggleShowPassword, isPending } =
		useLoginForm();

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
				<LoginHeader />

				<LoginAlerts reasonMessage={reasonMessage} loginError={loginError} />

				<form.Field name="email">
					{(field) => {
						const isInvalid = field.state.meta.errors && field.state.meta.errors.length > 0;
						return (
							<Field data-invalid={isInvalid}>
								<FieldLabel htmlFor="email">
									<FieldTitle className="text-sm font-normal text-neutral-900">Email</FieldTitle>
								</FieldLabel>
								<FieldContent>
									<div className="relative">
										<Input
											name={field.name}
											id="email"
											type="email"
											placeholder="e.g. johndoe@gmail.com"
											value={field.state.value}
											onChange={(e) => field.handleChange(e.target.value)}
											onBlur={field.handleBlur}
											disabled={isPending}
											aria-invalid={isInvalid}
											autoComplete="username"
											className="border-gray-200 bg-white focus-visible:ring-blue-500"
										/>
									</div>
								</FieldContent>
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
								<FieldLabel htmlFor="password">
									<FieldTitle className="text-sm font-normal text-neutral-900">Password</FieldTitle>
								</FieldLabel>
								<FieldContent>
									<div className="relative">
										<Input
											name={field.name}
											id="password"
											type={showPassword ? "text" : "password"}
											placeholder="••••••••"
											value={field.state.value}
											onChange={(e) => field.handleChange(e.target.value)}
											onBlur={field.handleBlur}
											disabled={isPending}
											aria-invalid={isInvalid}
											autoComplete="current-password"
											className="border-gray-200 bg-white focus-visible:ring-blue-500 pr-10"
										/>
										<Button
											type="button"
											variant="ghost"
											size="icon"
											className="absolute right-0 top-0 h-full px-3 py-2 text-zinc-600 hover:text-zinc-900 hover:bg-transparent"
											onClick={toggleShowPassword}
										>
											{showPassword ? (
												<RiEyeOffLine className="h-4 w-4" />
											) : (
												<RiEyeLine className="h-4 w-4" />
											)}
										</Button>
									</div>
								</FieldContent>
								{isInvalid && (
									<FieldError errors={field.state.meta.errors as Array<{ message?: string }>} />
								)}
							</Field>
						);
					}}
				</form.Field>

				<form.Subscribe selector={(state) => [state.isSubmitting]}>
					{([isSubmitting]) => (
						<Field className="pt-2">
							<Button
								type="submit"
								disabled={isPending || isSubmitting}
								className="w-full bg-blue-500 hover:bg-blue-600 text-white font-medium h-10 rounded-lg"
							>
								{isPending || isSubmitting ? (
									<>
										<RiLoader4Line className="mr-2 h-4 w-4 animate-spin shrink-0" />
										Logging in...
									</>
								) : (
									"Login"
								)}
							</Button>
						</Field>
					)}
				</form.Subscribe>
			</FieldGroup>
		</form>
	);
}
