import type { LucideIcon } from "lucide-react";

export type Agent = {
  id: string;
  name: string;
  color: string;
  icon: LucideIcon;
  desc: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  agent?: Agent;
  status?: "streaming" | "done";
  pendingReview?: boolean;
  turnId?: string;
};

export type PendingReview = {
  turnId: string;
  resolved: boolean;
  threadId: string;
  [key: string]: any;
};

export type SessionSummary = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
};
