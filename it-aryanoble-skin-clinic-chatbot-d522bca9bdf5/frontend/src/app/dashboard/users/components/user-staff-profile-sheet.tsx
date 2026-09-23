import { Button } from "@/components/ui/button";
import { Field, FieldContent, FieldLabel, FieldTitle } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { ConfirmationModal } from "@/components/shared/confirmation-modal";
import { RiDeleteBinLine, RiEyeLine, RiEyeOffLine, RiLoader4Line, RiEdit2Line, RiCheckLine } from "@remixicon/react";
import { useEffect, useState } from "react";
import { UserResponse } from "../api/types";
import { useDeleteUser, useUpdateStaffDetails, useUpdateUserRoles } from "../hooks/use-users";
import { useRoles } from "../hooks/use-roles";

export function UserStaffProfileSheet({
	isOpen,
	onOpenChange,
	staff,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	staff: UserResponse | null;
}) {
	const [isEditing, setIsEditing] = useState(false);
	const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
	const [name, setName] = useState("");
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [role, setRole] = useState("");
	const [showPassword, setShowPassword] = useState(false);

	const deleteUser = useDeleteUser();
	const updateStaff = useUpdateStaffDetails();
	const updateRoles = useUpdateUserRoles();
	const { data: rolesList = [] } = useRoles();

	useEffect(() => {
		if (staff && isOpen) {
			setTimeout(() => {
				setName(staff.name || "");
				setEmail(staff.email || "");
				setPassword("");
				setRole(staff.roles && staff.roles.length > 0 ? staff.roles[0].name : "Staff");
				setIsEditing(false);
				setShowPassword(false);
				setIsDeleteModalOpen(false);
			}, 0);
		}
	}, [staff, isOpen]);

	const handleDeleteClick = () => {
		if (!staff) return;
		setIsDeleteModalOpen(true);
	};

	const handleConfirmDelete = () => {
		if (!staff) return;
		deleteUser.mutate(staff.id, {
			onSuccess: () => {
				setIsDeleteModalOpen(false);
				onOpenChange(false);
			},
		});
	};

	const handleSave = () => {
		if (!staff) return;

		// If role changed, update role
		const currentRole = staff.roles && staff.roles.length > 0 ? staff.roles[0].name : "Staff";
		if (role && role !== currentRole) {
			updateRoles.mutate({ userId: staff.id, roles: [role] });
		}

		updateStaff.mutate(
			{
				userId: staff.id,
				data: {
					name,
					email,
					...(password ? { password } : {}),
				},
			},
			{
				onSuccess: () => setIsEditing(false),
			},
		);
	};

	return (
		<Sheet open={isOpen} onOpenChange={onOpenChange}>
			<SheetContent className="sm:max-w-100 p-0 flex flex-col h-full bg-white gap-0">
				<SheetHeader className="p-4 border-b flex flex-row items-center">
					<SheetTitle className="text-base font-medium">
						{isEditing ? "Edit Profile" : "User Profile"}
					</SheetTitle>
				</SheetHeader>

				{staff && (
					<>
						<div className="flex-1 overflow-y-auto pb-6">
							<div className="flex flex-col pb-4">
								{/* Details Section */}
								<div className="p-6 m-0 flex flex-col gap-6">
									<Field>
										<FieldLabel>
											<FieldTitle>Name</FieldTitle>
										</FieldLabel>
										<FieldContent>
											{isEditing ? (
												<div className="relative">
													<Input
														value={name}
														onChange={(e) => setName(e.target.value)}
														className="border-gray-200 bg-white focus-visible:ring-blue-500"
													/>
												</div>
											) : (
												<span className="text-sm text-gray-900">{staff.name}</span>
											)}
										</FieldContent>
									</Field>

									<Field>
										<FieldLabel>
											<FieldTitle>Role</FieldTitle>
										</FieldLabel>
										<FieldContent>
											{isEditing ? (
												<Select value={role} onValueChange={(val) => setRole(val ?? "")}>
													<SelectTrigger className="w-full border-gray-200 bg-white text-gray-700">
														<SelectValue placeholder="Select one role" />
													</SelectTrigger>
													<SelectContent alignItemWithTrigger={false} sideOffset={4}>
														{rolesList.length === 0 ? (
															<SelectItem value="Staff">Staff</SelectItem>
														) : (
															rolesList.map((r) => (
																<SelectItem key={r.id} value={r.name}>
																	{r.name}
																</SelectItem>
															))
														)}
													</SelectContent>
												</Select>
											) : (
												<Badge
													variant="secondary"
													className="bg-blue-50 text-blue-700 border-blue-200 font-medium text-xs uppercase"
												>
													{staff.roles && staff.roles.length > 0 ? staff.roles[0].name : "Staff"}
												</Badge>
											)}
										</FieldContent>
									</Field>

									<Field>
										<FieldLabel>
											<FieldTitle>Email</FieldTitle>
										</FieldLabel>
										<FieldContent>
											{isEditing ? (
												<div className="relative">
													<Input
														value={email}
														onChange={(e) => setEmail(e.target.value)}
														type="email"
														className="border-gray-200 bg-white focus-visible:ring-blue-500"
														autoComplete="off"
													/>
												</div>
											) : (
												<span className="text-sm text-gray-900">{staff.email}</span>
											)}
										</FieldContent>
									</Field>

									<Field>
										<FieldLabel>
											<FieldTitle>{isEditing ? "New Password" : "Password"}</FieldTitle>
										</FieldLabel>
										<FieldContent>
											{isEditing ? (
												<div className="relative">
													<Input
														value={password}
														onChange={(e) => setPassword(e.target.value)}
														type={showPassword ? "text" : "password"}
														placeholder="Leave blank to keep"
														className="border-gray-200 bg-white focus-visible:ring-blue-500 pr-10"
														autoComplete="new-password"
													/>
													<Button
														variant="ghost"
														size="icon"
														className="absolute right-0 top-0 text-zinc-600 hover:text-zinc-900"
														onClick={() => setShowPassword(!showPassword)}
														type="button"
													>
														{showPassword ? (
															<RiEyeOffLine className="h-4 w-4" />
														) : (
															<RiEyeLine className="h-4 w-4" />
														)}
													</Button>
												</div>
											) : (
												<span className="text-sm text-gray-900">********</span>
											)}
										</FieldContent>
									</Field>

									{!isEditing && (
										<>
											<Field>
												<FieldLabel>
													<FieldTitle>Tokens Used This Month</FieldTitle>
												</FieldLabel>
												<FieldContent>
													<span className="text-sm text-gray-900 font-medium">
														{(staff.tokens_used ?? 0).toLocaleString()} tokens
													</span>
												</FieldContent>
											</Field>

											<Field>
												<FieldLabel>
													<FieldTitle>Date & Time Created</FieldTitle>
												</FieldLabel>
												<FieldContent>
													<span className="text-sm text-gray-900">
														{new Date(staff.created_at).toLocaleString("en-US", {
															year: "numeric",
															month: "numeric",
															day: "numeric",
															hour: "numeric",
															minute: "numeric",
															hour12: true,
														})}
													</span>
												</FieldContent>
											</Field>
										</>
									)}
								</div>
							</div>
						</div>

						{isEditing ? (
							<div className="p-4 border-t border-gray-200 bg-white flex justify-end gap-3">
								<Button
									type="button"
									variant="outline"
									className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
									onClick={() => {
										setIsEditing(false);
										if (staff) {
											setName(staff.name || "");
											setEmail(staff.email || "");
											setPassword("");
										}
									}}
								>
									Cancel
								</Button>
								<Button
									type="button"
									className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none disabled:opacity-50"
									onClick={handleSave}
									disabled={updateStaff.isPending}
								>
									{updateStaff.isPending ? (
										<RiLoader4Line className="mr-1.5 h-4 w-4 animate-spin shrink-0" />
									) : (
										<RiCheckLine className="mr-1.5 h-4 w-4 shrink-0" />
									)}
									{updateStaff.isPending ? "Saving..." : "Save Changes"}
								</Button>
							</div>
						) : (
							<div className="p-4 border-t border-gray-200 bg-white flex justify-end gap-3">
								<Button
									type="button"
									variant="outline"
									className="border-red-200 text-red-600 hover:bg-red-50 hover:border-red-300 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none disabled:opacity-50"
									onClick={handleDeleteClick}
									disabled={deleteUser.isPending}
								>
									<RiDeleteBinLine className="mr-1.5 h-4 w-4 shrink-0" />
									Delete User
								</Button>
								<Button
									type="button"
									className="bg-blue-600 text-white hover:bg-blue-700 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
									onClick={() => setIsEditing(true)}
								>
									<RiEdit2Line className="mr-1.5 h-4 w-4 shrink-0" />
									Edit Profile
								</Button>
							</div>
						)}
					</>
				)}
			</SheetContent>

			{/* Delete User Confirmation Modal */}
			<ConfirmationModal
				isOpen={isDeleteModalOpen}
				onOpenChange={setIsDeleteModalOpen}
				title="Delete User"
				description={`Are you sure you want to delete ${staff?.name || "this user"}? This action cannot be undone.`}
				confirmText="Delete User"
				variant="destructive"
				isLoading={deleteUser.isPending}
				onConfirm={handleConfirmDelete}
			/>
		</Sheet>
	);
}
