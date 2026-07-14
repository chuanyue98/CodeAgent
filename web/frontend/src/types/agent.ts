export type PermissionMode = 'workspace-write' | 'read-only';
export type ApprovalDecision = 'accept' | 'acceptForSession' | 'decline' | 'cancel';

export interface ProviderCapabilities {
  providerId: string;
  displayName: string;
  available: boolean;
  unavailableReason: string | null;
  supportsResume: boolean;
  supportsSteer: boolean;
  supportsCancel: boolean;
  supportsApprovals: boolean;
  supportsFileDiff: boolean;
  supportsToolEvents: boolean;
  supportsAttachments: boolean;
  supportsModelSwitch: boolean;
}

export interface AgentSession {
  id: string;
  provider: string;
  providerSessionId: string;
  projectId: string;
  cwd: string;
  title: string | null;
  model: string | null;
  permissionMode: PermissionMode;
  createdAt: string;
  updatedAt: string;
  status: 'starting' | 'ready' | 'busy' | 'disconnected' | 'error' | 'closed';
  lastSequence: number;
  capabilitySnapshot: ProviderCapabilities;
}

export interface AgentEvent {
  type: string;
  sequence: number;
  timestamp: string;
  sessionId: string;
  turnId: string | null;
  itemId: string | null;
  data: Record<string, unknown>;
}

export interface AgentAck {
  type: 'ack';
  requestId: string;
  command: string;
  result: Record<string, unknown>;
}

export interface AgentError {
  type: 'error';
  requestId?: string | null;
  sessionId?: string | null;
  turnId?: string | null;
  code: string;
  message: string;
  retryable: boolean;
}

export interface AgentInput {
  type: 'text';
  text: string;
}

export type AgentCommand =
  | { type: 'session.resume'; requestId: string; sessionId: string }
  | { type: 'turn.start'; requestId: string; sessionId: string; input: AgentInput[] }
  | { type: 'turn.steer'; requestId: string; sessionId: string; turnId: string; input: AgentInput[] }
  | { type: 'turn.cancel'; requestId: string; sessionId: string; turnId: string }
  | { type: 'approval.respond'; requestId: string; sessionId: string; approvalId: string; decision: ApprovalDecision };

export interface ApprovalRequest {
  id: string;
  kind: string;
  command?: string | null;
  commandActions?: unknown[] | null;
  cwd?: string | null;
  reason?: string | null;
  grantRoot?: string | null;
}
