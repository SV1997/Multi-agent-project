import { Scale, Users, Cpu, Code2, LifeBuoy } from "lucide-react";
import type { Agent } from "./types";

export const COLORS = {
  ink: "#0B0F17",
  panel: "#131A26",
  raised: "#1B2433",
  paper: "#E7E9EE",
  muted: "#7C8699",
  faint: "#4A5468",
  hairline: "#263047",
  signal: "#F2A93C",
  error: "#F25C54",
};

export const AGENTS: Agent[] = [
  { id: "legal_agent", name: "Legal", color: "#9B8CFF", icon: Scale, desc: "Contracts, policy, compliance" },
  { id: "hr_agent", name: "HR", color: "#FF8FA3", icon: Users, desc: "Benefits, leave, onboarding" },
  { id: "engineering_agent", name: "Engineering", color: "#58C4DC", icon: Cpu, desc: "Infra, architecture, incidents" },
  { id: "coding_agent", name: "Coding", color: "#8DD672", icon: Code2, desc: "Snippets, APIs, standards" },
  { id: "support_agent", name: "Support", color: "#F2A93C", icon: LifeBuoy, desc: "Tickets, how-tos, triage" },
];

export const STAGES = [
  { id: "classify_domain", label: "Classifying" },
  { id: "check_authorization", label: "Permission check" },
  { id: "agent", label: "Routing" },
  { id: "retrieve", label: "Retrieving" },
  { id: "done", label: "Done" },
];
