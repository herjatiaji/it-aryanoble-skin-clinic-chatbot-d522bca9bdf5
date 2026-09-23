"use client";

import { Suspense } from "react";
import { LoginForm } from "./components/login-form";
import { LoginFormSkeleton } from "./components/skeletons/login-form-skeleton";

export default function LoginPage() {
	return (
		<div className="flex min-h-svh w-full items-center justify-center p-4 bg-white">
			<div className="w-full max-w-100 rounded-lg border border-gray-200 bg-white p-6 shadow-none">
				<Suspense fallback={<LoginFormSkeleton />}>
					<LoginForm />
				</Suspense>
			</div>
		</div>
	);
}
