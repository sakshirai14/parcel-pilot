import type { ChatResponse, ActionProposal, AuditLogEntry } from '../types';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function sendMessage(message: string, userId: string): Promise<ChatResponse> {
  const response = await fetch(`${BASE_URL}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, user_id: userId }),
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || 'Failed to send message');
  }
  return response.json();
}

export async function confirmAction(
  actionId: string,
  userId: string,
  clientPayload?: Record<string, any>
): Promise<{ status: string; message: string; action_id?: string }> {
  const response = await fetch(`${BASE_URL}/api/actions/${actionId}/confirm`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ user_id: userId, client_payload: clientPayload }),
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || 'Failed to confirm action');
  }
  return response.json();
}

export async function cancelAction(
  actionId: string,
  userId: string
): Promise<{ status: string; message: string; action_id: string }> {
  const response = await fetch(`${BASE_URL}/api/actions/${actionId}/cancel`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ user_id: userId }),
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || 'Failed to cancel action');
  }
  return response.json();
}

export async function getActionProposal(actionId: string): Promise<ActionProposal> {
  const response = await fetch(`${BASE_URL}/api/actions/${actionId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch action proposal ${actionId}`);
  }
  return response.json();
}

export async function getActionAudit(actionId: string): Promise<AuditLogEntry[]> {
  const response = await fetch(`${BASE_URL}/api/actions/${actionId}/audit`);
  if (!response.ok) {
    throw new Error(`Failed to fetch audit log for action ${actionId}`);
  }
  return response.json();
}

export async function getBackendConfig(): Promise<{ llm_mode: string; llm_model: string }> {
  const response = await fetch(`${BASE_URL}/api/config`);
  if (!response.ok) {
    throw new Error('Failed to fetch backend configuration');
  }
  return response.json();
}
