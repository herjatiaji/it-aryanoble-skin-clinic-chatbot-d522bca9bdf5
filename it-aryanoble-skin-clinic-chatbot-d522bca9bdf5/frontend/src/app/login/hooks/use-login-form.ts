import { loginSchema, type LoginValues } from "@/app/login/components/login-schema";
import { useLogin } from "@/app/login/hooks/use-login";
import { getErrorMessage } from "@/lib/utils";
import { useForm } from "@tanstack/react-form";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

export function useLoginForm() {
	const router = useRouter();
	const searchParams = useSearchParams();
	const [loginError, setLoginError] = useState<string | null>(null);
	const [showPassword, setShowPassword] = useState(false);
	const { mutate: login, isPending } = useLogin();

	useEffect(() => {
		if (typeof window !== "undefined") {
			sessionStorage.removeItem("is_logging_out");
		}
	}, []);

	const reason = searchParams.get("reason");
	const reasonMessage =
		reason === "idle"
			? "You were logged out due to inactivity."
			: reason === "session_expired"
				? "Your session has expired. Please log in again."
				: null;

	useEffect(() => {
		if (reasonMessage) {
			toast.warning(reasonMessage);
		}
	}, [reasonMessage]);

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

			await new Promise((resolve) => setTimeout(resolve, 800));

			login(credentials, {
				onSuccess: ({ userProfile }) => {
					const fromParam = searchParams.get("from");
					let target = "/dashboard/knowledge";

					if (fromParam && fromParam.startsWith("/") && !fromParam.startsWith("/login")) {
						target = fromParam;
					}

					router.push(target);

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

	const toggleShowPassword = () => setShowPassword((prev) => !prev);

	return {
		form,
		loginError,
		reasonMessage,
		showPassword,
		toggleShowPassword,
		isPending,
	};
}
