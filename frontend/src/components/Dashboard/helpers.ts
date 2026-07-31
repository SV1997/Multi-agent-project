import { AGENTS } from "./constants";
import type { Agent } from "./types";

const STAGE_BY_NODE: Record<string, string> = {
  classify_domain: "classify_domain",
  check_authorization: "check_authorization",
  retrieve: "retrieve",
  legal_agent: "agent",
  hr_agent: "agent",
  support_agent: "agent",
  coding_agent: "agent",
  engineering_agent: "agent",
};

export function mapNodeNameToStage(nodeName: string): string {
  return STAGE_BY_NODE[nodeName] ?? "";
}

export function mapNodeNameToAgent(nodeName: string): Agent | null {
  return AGENTS.find((agent) => agent.id === nodeName) ?? null;
}
