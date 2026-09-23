"use client";

import { useForm } from "@tanstack/react-form";
import { useEffect } from "react";
import { z } from "zod";
import { BranchResponse } from "../api/types";
import { editTokenSchema } from "../components/branch-schema";
import { useUpdateBranch } from "./use-branches";

interface UseEditBranchTokenFormProps {
	branch: BranchResponse;
	isOpen: boolean;
	onSuccess?: () => void;
}

export function useEditBranchTokenForm({ branch, isOpen, onSuccess }: UseEditBranchTokenFormProps) {
	const updateBranch = useUpdateBranch();
	const tokenLimitValue = (branch.token_limit ?? branch.tokensMonth ?? 0).toString();

	const form = useForm({
		defaultValues: {
			token_limit: tokenLimitValue,
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
						onSuccess?.();
						formApi.reset();
					},
				},
			);
		},
	});

	// Reset form when opened or when branch data changes
	useEffect(() => {
		if (isOpen) {
			form.reset();
		}
	}, [isOpen, branch.token_limit, branch.tokensMonth, form]);

	const handleResetToGlobal = () => {
		updateBranch.mutate(
			{
				id: branch.id,
				data: {
					reset_to_global: true,
				},
			},
			{
				onSuccess: () => {
					onSuccess?.();
					form.reset();
				},
			},
		);
	};

	return {
		form,
		isPending: updateBranch.isPending,
		handleResetToGlobal,
	};
}
