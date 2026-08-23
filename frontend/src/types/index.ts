export type UserRole = 'CUSTOMER' | 'SUPPORT_AGENT' | 'OPERATIONS_ADMIN';

export interface UserContext {
  role: UserRole;
  customer_account_id?: string;
  user_id?: string;
}

export interface Citation {
  type: 'DOCUMENT' | 'OPERATIONAL_DATA';
  source_name: string;
  description: string;
  page?: number;
  authority_status?: string;
}

export interface AuthorityResolution {
  conflict_detected: boolean;
  governing_source?: string;
  reason?: string;
  conflict_message?: string;
}

export interface ToolActivity {
  tool: string;
  status: 'RUNNING' | 'COMPLETED' | 'FAILED';
}

export interface ActionProposal {
  action_id: string;
  action_type: string;
  account_id?: string;
  ticket_id?: string;
  order_id?: string;
  summary: string;
  reason: string;
  proposed_changes: Record<string, any>;
  created_by: string;
  created_at: string;
  status: string;
  expires_at: string;
}

export interface ChatResponse {
  answer: string;
  status: string;
  citations: Citation[];
  tools_used: { tool: string; status: string }[];
  requires_human_review: boolean;
  requires_confirmation: boolean;
  proposed_action?: ActionProposal;
  authority_resolution?: AuthorityResolution;
}

export interface ChatRequest {
  message: string;
  user_id: string;
}

export interface ConfirmActionRequest {
  user_id: string;
  client_payload?: Record<string, any>;
}

export interface ExecuteActionRequest {
  user_id: string;
  action_id: string;
  client_payload?: Record<string, any>;
}

export interface AuditLogEntry {
  audit_id?: number;
  action_id: string;
  user_id: string;
  role: string;
  account_id?: string;
  ticket_id?: string;
  order_id?: string;
  action_type: string;
  previous_state?: string;
  proposed_state?: string;
  final_state?: string;
  timestamp: string;
  result: string;
  authorization_result: string;
}
