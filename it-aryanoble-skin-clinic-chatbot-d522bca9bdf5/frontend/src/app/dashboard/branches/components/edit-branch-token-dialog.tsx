"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { RiEdit2Line, RiLoader4Line } from "@remixicon/react";
import { useUpdateBranch } from "../hooks/use-branches";
import { useForm } from "@tanstack/react-form";
import { Field, FieldLabel, FieldError } from "@/components/ui/field";
import { z } from "zod";
import { BranchResponse } from "../../configuration/api/types";
import { editTokenSchema } from "./branch-schema";



interface EditBranchTokenDialogProps {
	branch: BranchResponse;
}

export function EditBranchTokenDialog({ branch }: EditBranchTokenDialogProps) {
	const [open, setOpen] = React.useState(false);
	const updateBranch = useUpdateBranch();

	const form = useForm({
		defaultValues: {
			token_limit: branch.tokensMonth.toString(),
		} as z.input<typeof editTokenSchema>,
		validators: {
			onChange: editTokenSchema,
		},
		onSubmit: async ({ value, formApi }) => {
			const parsedData = editTokenSchema.parse(value);

			updateBranch.mutate(
				{
					id: branch.id,
					data: {
						token_limit: parsedData.token_limit,
					},
				},
				{
					onSuccess: () => {
						setOpen(false);
						formApi.reset();
					},
				}
			);
		},
	});

	// Reset form when opened with latest branch data
	React.useEffect(() => {
		if (open) {
			form.reset();
		}
	}, [open, branch.tokensMonth, form]);

	return (
		<Dialog open={open} onOpenChange={setOpen}>
			<DialogTrigger
				render={
					<Button
						variant="outline"
						className="bg-white border-black-50 text-black-500 hover:bg-zinc-50 hover:text-black-600 h-9 px-4 py-2 rounded-lg shadow-none text-sm font-medium"
					/>
				}
			>
				<RiEdit2Line className="size-4 mr-2" />
				Edit Token Limit
			</DialogTrigger>
			<DialogContent className="sm:max-w-md w-full bg-white p-0">
				<DialogHeader className="p-4 border-b border-black-50">
					<DialogTitle className="text-base font-medium text-black-500 text-left">
						Edit Branch Token Limit
					</DialogTitle>
				</DialogHeader>

				<form
					onSubmit={(e) => {
						e.preventDefault();
						e.stopPropagation();
						void form.handleSubmit();
					}}
					className="flex flex-col"
				>
					<div className="p-4 flex flex-col gap-4">
						<form.Field name="token_limit">
							{(field) => {
								const isInvalid = field.state.meta.errors && field.state.meta.errors.length > 0;
								return (
									<Field data-invalid={isInvalid}>
										<FieldLabel htmlFor="token_limit">Token Limit</FieldLabel>
										<div className="relative">
											<Input
												name={field.name}
												id="token_limit"
												type="number"
												placeholder="1000"
												className="h-10 rounded-lg border-black-50 bg-white text-sm text-black-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
												value={field.state.value}
												onChange={(e) => field.handleChange(e.target.value)}
												onBlur={field.handleBlur}
												aria-invalid={isInvalid}
											/>
											<span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-black-200 pointer-events-none">
												per month
											</span>
										</div>
										{isInvalid && (
											<FieldError errors={field.state.meta.errors as Array<{ message?: string }>} />
										)}
									</Field>
								);
							}}
						</form.Field>
					</div>

					<div className="p-4 border-t border-black-50 flex justify-end gap-3 bg-white rounded-b-xl">
						<Button
							type="button"
							variant="outline"
							className="border-blue-500 text-blue-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg font-medium px-5 shadow-none"
							onClick={() => setOpen(false)}
						>
							Cancel
						</Button>
						<form.Subscribe selector={(state) => [state.canSubmit, state.isSubmitting]}>
							{([canSubmit, isSubmitting]) => (
								<Button
									type="submit"
									disabled={!canSubmit || updateBranch.isPending || isSubmitting}
									className="bg-blue-600 text-white hover:bg-blue-700 rounded-lg font-medium px-5 shadow-none disabled:opacity-50 disabled:bg-black-50 disabled:text-black-200"
								>
									{updateBranch.isPending || isSubmitting ? (
										<RiLoader4Line className="mr-2 h-4 w-4 animate-spin shrink-0" />
									) : null}
									{updateBranch.isPending || isSubmitting ? "Saving..." : "Save Changes"}
								</Button>
							)}
						</form.Subscribe>
					</div>
				</form>
			</DialogContent>
		</Dialog>
	);
}
