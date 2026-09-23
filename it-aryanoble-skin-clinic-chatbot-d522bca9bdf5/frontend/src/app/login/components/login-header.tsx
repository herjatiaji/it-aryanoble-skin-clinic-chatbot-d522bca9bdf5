import { RiRobot2Line } from "@remixicon/react";

export function LoginHeader() {
	return (
		<div className="flex flex-col items-center text-center">
			<div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-blue-50">
				<RiRobot2Line className="h-7 w-7 text-blue-600" />
			</div>
			<h1 className="mb-1 text-xl font-semibold text-foreground">Hello, welcome back</h1>
			<p className="text-sm text-muted-foreground">
				Sign in to manage conversations, knowledge, and chatbot performance.
			</p>
		</div>
	);
}
