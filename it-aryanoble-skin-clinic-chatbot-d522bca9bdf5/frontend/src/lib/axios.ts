import axios from "axios";

// Always use "/api" as the base URL for the client.
// Browser requests will hit the same-origin Next.js proxy (/api/* -> http://backend:8000/api/*).
let defaultBaseURL = "/api";
const publicApi = process.env.NEXT_PUBLIC_API_URL;
if (publicApi && !publicApi.includes("localhost") && !publicApi.includes("127.0.0.1") && !publicApi.includes("backend")) {
	defaultBaseURL = publicApi;
}

export const api = axios.create({
	baseURL: defaultBaseURL,
	// Ensure cookies are sent with every request
	withCredentials: true,
});

// Request interceptor to add any needed headers and handle SSR container routing
api.interceptors.request.use(
	(config) => {
		// If running on the server during SSR, route to internal backend container
		if (typeof window === "undefined" && config.url && !config.url.startsWith("http")) {
			const internalBackend = process.env.INTERNAL_BACKEND_URL || "http://backend:8000";
			const cleanBase = internalBackend.replace(/\/api\/?$/, "");
			const cleanPath = config.url.startsWith("/") ? config.url : `/${config.url}`;
			config.baseURL = undefined;
			config.url = `${cleanBase}/api${cleanPath}`;
		}
		return config;
	},
	(error) => {
		return Promise.reject(error);
	},
);

// Concurrency queue for handling silent token refresh
let isRefreshing = false;
let failedQueue: Array<{
	resolve: (value?: unknown) => void;
	reject: (reason?: unknown) => void;
}> = [];

const processQueue = (error: unknown = null) => {
	failedQueue.forEach((prom) => {
		if (error) {
			prom.reject(error);
		} else {
			prom.resolve();
		}
	});
	failedQueue = [];
};

// Response interceptor for handling global errors and silent token refresh
api.interceptors.response.use(
	(response) => {
		return response;
	},
	async (error) => {
		const originalRequest = error.config;

		// Check if error is 401 Unauthorized and not already retried
		if (error.response && error.response.status === 401 && originalRequest) {
			const isLoggingOut =
				typeof window !== "undefined" && sessionStorage.getItem("is_logging_out") === "true";

			if (isLoggingOut) {
				return Promise.reject(error);
			}

			const url = originalRequest.url || "";
			const isAuthEndpoint =
				url.includes("/auth/login") ||
				url.includes("/auth/refresh") ||
				url.includes("/auth/logout");

			// For auth endpoint failures or requests that were already retried once
			if (isAuthEndpoint || originalRequest._retry) {
				if (
					(url.includes("/auth/refresh") || originalRequest._retry) &&
					typeof window !== "undefined" &&
					window.location.pathname !== "/login"
				) {
					const currentPath = window.location.pathname + window.location.search;
					const fromParam = currentPath !== "/" ? `&from=${encodeURIComponent(currentPath)}` : "";
					window.location.href = `/login?reason=session_expired${fromParam}`;
				}
				return Promise.reject(error);
			}

			if (isRefreshing) {
				return new Promise((resolve, reject) => {
					failedQueue.push({ resolve, reject });
				})
					.then(() => api(originalRequest))
					.catch((err) => Promise.reject(err));
			}

			originalRequest._retry = true;
			isRefreshing = true;

			try {
				await api.post("/auth/refresh");
				processQueue(null);
				return api(originalRequest);
			} catch (refreshError) {
				processQueue(refreshError);
				if (typeof window !== "undefined" && window.location.pathname !== "/login") {
					const currentPath = window.location.pathname + window.location.search;
					const fromParam = currentPath !== "/" ? `&from=${encodeURIComponent(currentPath)}` : "";
					window.location.href = `/login?reason=session_expired${fromParam}`;
				}
				return Promise.reject(refreshError);
			} finally {
				isRefreshing = false;
			}
		}

		return Promise.reject(error);
	},
);
