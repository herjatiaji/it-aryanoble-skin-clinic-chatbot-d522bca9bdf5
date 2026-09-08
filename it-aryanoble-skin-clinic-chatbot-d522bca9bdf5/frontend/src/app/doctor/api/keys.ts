export const doctorChatKeys = {
  all: ["doctor-chats"] as const,
  sessions: () => [...doctorChatKeys.all, "sessions"] as const,
  session: (id: string) => [...doctorChatKeys.sessions(), id] as const,
  messages: (sessionId: string) => [...doctorChatKeys.session(sessionId), "messages"] as const,
};
