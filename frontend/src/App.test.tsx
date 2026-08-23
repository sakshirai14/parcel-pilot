import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import App from './App';
import * as api from './services/api';

// Mock the API layer
vi.mock('./services/api', () => {
  return {
    sendMessage: vi.fn(),
    confirmAction: vi.fn(),
    cancelAction: vi.fn(),
    getActionProposal: vi.fn(),
    getActionAudit: vi.fn(),
    getBackendConfig: vi.fn(),
  };
});

describe('ParcelPilot Chatbot UI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getBackendConfig).mockResolvedValue({
      llm_mode: 'mock',
      llm_model: 'gemini-3.7-flash',
    });
  });

  it('1. Renders welcome message and layout', () => {
    render(<App />);
    expect(screen.getAllByText(/ParcelPilot AI/i)[0]).toBeInTheDocument();
    expect(screen.getByText(/Ask me about B2B logistics/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Ask ParcelPilot anything.../i)).toBeInTheDocument();
  });

  it('2. Shows loading state during message sending', async () => {
    let resolveMessage: any;
    const promise = new Promise<any>((resolve) => {
      resolveMessage = resolve;
    });
    vi.mocked(api.sendMessage).mockReturnValue(promise);

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask ParcelPilot anything.../i);

    fireEvent.change(textarea, { target: { value: 'Test message' } });
    fireEvent.click(screen.getByTitle('Send Message'));

    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
    
    resolveMessage({ answer: 'Mock reply', status: 'ANSWERED', citations: [], tools_used: [] });
    await act(async () => {
      await promise;
    });
  });

  it('3. Renders chat messages and high-level tool activity is hidden', async () => {
    vi.mocked(api.sendMessage).mockResolvedValue({
      answer: 'This is the answer.',
      status: 'ANSWERED',
      citations: [],
      tools_used: [
        { tool: 'lookup_operational_data', status: 'completed' },
        { tool: 'calculate_entitlement', status: 'completed' },
      ],
      requires_human_review: false,
      requires_confirmation: false,
    });

    render(<App />);
    const supportAgentRadio = screen.getByLabelText('Support Agent');
    fireEvent.click(supportAgentRadio);

    const textarea = screen.getByPlaceholderText(/Ask ParcelPilot anything.../i);
    fireEvent.change(textarea, { target: { value: 'Cancel fee check' } });
    fireEvent.click(screen.getByTitle('Send Message'));

    await waitFor(() => {
      expect(screen.getByText('This is the answer.')).toBeInTheDocument();
    });

    expect(screen.queryByTestId('tool-activity-panel')).not.toBeInTheDocument();
    expect(screen.queryByText('Lookup Operational Data')).not.toBeInTheDocument();
  });

  it('4. Renders document citations is hidden completely', async () => {
    vi.mocked(api.sendMessage).mockResolvedValue({
      answer: 'Citations answer.',
      status: 'ANSWERED',
      citations: [
        { type: 'DOCUMENT', source_name: '05_Northstar_Logistics_Enterprise_Agreement.pdf', page: 3, description: 'Sect 2', authority_status: 'CURRENT' },
      ],
      tools_used: [],
      requires_human_review: false,
      requires_confirmation: false,
    });

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask ParcelPilot anything.../i);
    fireEvent.change(textarea, { target: { value: 'Give me citations' } });
    fireEvent.click(screen.getByTitle('Send Message'));

    await waitFor(() => {
      expect(screen.getByText('Citations answer.')).toBeInTheDocument();
    });

    expect(screen.queryByTestId('citations-container')).not.toBeInTheDocument();
  });

  it('5. Renders special status badge (e.g. UNAUTHORIZED or CONFLICT) is hidden', async () => {
    vi.mocked(api.sendMessage).mockResolvedValue({
      answer: 'Access denied to this resource.',
      status: 'UNAUTHORIZED',
      citations: [],
      tools_used: [],
      requires_human_review: false,
      requires_confirmation: false,
    });

    render(<App />);
    const supportAgentRadio = screen.getByLabelText('Support Agent');
    fireEvent.click(supportAgentRadio);

    const textarea = screen.getByPlaceholderText(/Ask ParcelPilot anything.../i);
    fireEvent.change(textarea, { target: { value: 'Access secret file' } });
    fireEvent.click(screen.getByTitle('Send Message'));

    await waitFor(() => {
      expect(screen.getByText('Access denied to this resource.')).toBeInTheDocument();
    });

    expect(screen.queryByText(/State:/i)).not.toBeInTheDocument();
  });

  it('6. Confirmation cards are rendered in the DOM', async () => {
    const proposal = {
      action_id: 'ACT-1234',
      action_type: 'CREATE_ESCALATION',
      summary: 'Prepare CREATE_ESCALATION for TKT-501',
      reason: 'SLA breach escalation',
      proposed_changes: { ticket_id: 'TKT-501', reason: 'SLA breach escalation', priority: 'P1' },
      created_by: 'support-demo',
      created_at: '2026-08-22 13:00:00',
      status: 'PENDING_CONFIRMATION',
      expires_at: '2026-08-22 13:15:00',
    };

    vi.mocked(api.sendMessage).mockResolvedValue({
      answer: 'I prepared the escalation.',
      status: 'PENDING_CONFIRMATION',
      citations: [],
      tools_used: [],
      requires_human_review: false,
      requires_confirmation: true,
      proposed_action: proposal,
    });

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask ParcelPilot anything.../i);
    fireEvent.change(textarea, { target: { value: 'Escalate ticket' } });
    fireEvent.click(screen.getByTitle('Send Message'));

    await waitFor(() => {
      expect(screen.getByText('I prepared the escalation.')).toBeInTheDocument();
    });
    expect(screen.getByTestId('confirmation-card')).toBeInTheDocument();
    expect(screen.getByText('Action Requires Confirmation')).toBeInTheDocument();
    expect(screen.getByText('ACT-1234')).toBeInTheDocument();
  });

  it('7. Renders confirm button for action confirmation', async () => {
    const proposal = {
      action_id: 'ACT-1234',
      action_type: 'CREATE_ESCALATION',
      summary: 'Prepare CREATE_ESCALATION for TKT-501',
      reason: 'SLA breach escalation',
      proposed_changes: { ticket_id: 'TKT-501', reason: 'SLA breach escalation', priority: 'P1' },
      created_by: 'support-demo',
      created_at: '2026-08-22 13:00:00',
      status: 'PENDING_CONFIRMATION',
      expires_at: '2026-08-22 13:15:00',
    };

    vi.mocked(api.sendMessage).mockResolvedValue({
      answer: 'I prepared the escalation.',
      status: 'PENDING_CONFIRMATION',
      citations: [],
      tools_used: [],
      requires_human_review: false,
      requires_confirmation: true,
      proposed_action: proposal,
    });

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask ParcelPilot anything.../i);
    fireEvent.change(textarea, { target: { value: 'Escalate ticket' } });
    fireEvent.click(screen.getByTitle('Send Message'));

    await waitFor(() => {
      expect(screen.getByText('I prepared the escalation.')).toBeInTheDocument();
    });

    expect(screen.getByTestId('confirm-btn')).toBeInTheDocument();
  });

  it('8. Renders cancel button for action cancellation', async () => {
    const proposal = {
      action_id: 'ACT-1234',
      action_type: 'CREATE_ESCALATION',
      summary: 'Prepare CREATE_ESCALATION for TKT-501',
      reason: 'SLA breach escalation',
      proposed_changes: { ticket_id: 'TKT-501', reason: 'SLA breach escalation', priority: 'P1' },
      created_by: 'support-demo',
      created_at: '2026-08-22 13:00:00',
      status: 'PENDING_CONFIRMATION',
      expires_at: '2026-08-22 13:15:00',
    };

    vi.mocked(api.sendMessage).mockResolvedValue({
      answer: 'I prepared the escalation.',
      status: 'PENDING_CONFIRMATION',
      citations: [],
      tools_used: [],
      requires_human_review: false,
      requires_confirmation: true,
      proposed_action: proposal,
    });

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask ParcelPilot anything.../i);
    fireEvent.change(textarea, { target: { value: 'Escalate ticket' } });
    fireEvent.click(screen.getByTitle('Send Message'));

    await waitFor(() => {
      expect(screen.getByText('I prepared the escalation.')).toBeInTheDocument();
    });

    expect(screen.getByTestId('cancel-btn')).toBeInTheDocument();
  });

  it('9. Displays error toast when API fails', async () => {
    vi.mocked(api.sendMessage).mockRejectedValue(new Error('Network error. Backend down.'));

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask ParcelPilot anything.../i);
    fireEvent.change(textarea, { target: { value: 'Hello' } });
    fireEvent.click(screen.getByTitle('Send Message'));

    await waitFor(() => {
      expect(screen.getByTestId('error-toast')).toBeInTheDocument();
    });
    expect(screen.getByText('Network error. Backend down.')).toBeInTheDocument();
  });

  it('10. Renders context switcher and handles click events', () => {
    render(<App />);
    
    expect(screen.getByTestId('context-switcher')).toBeInTheDocument();
    expect(screen.getByText('Support Agent')).toBeInTheDocument();

    const agentRadio = screen.getByLabelText('Support Agent');
    fireEvent.click(agentRadio);

    expect(agentRadio).toBeChecked();
  });

  it('11. Customer UI hides internal details completely', async () => {
    vi.mocked(api.sendMessage).mockResolvedValue({
      answer: 'Yes, you can cancel ORD-1001 without a fee.',
      status: 'CONFLICT_REQUIRES_REVIEW',
      citations: [
        { type: 'DOCUMENT', source_name: '05_Northstar_Logistics_Enterprise_Agreement.pdf', page: 1, description: 'Sect 2', authority_status: 'CURRENT' },
      ],
      tools_used: [
        { tool: 'lookup_operational_data', status: 'completed' },
      ],
      requires_human_review: true,
      requires_confirmation: false,
    });

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask ParcelPilot anything.../i);
    fireEvent.change(textarea, { target: { value: 'Can Northstar cancel ORD-1001 without a cancellation fee?' } });
    fireEvent.click(screen.getByTitle('Send Message'));

    await waitFor(() => {
      expect(screen.getByText('Yes, you can cancel ORD-1001 without a fee.')).toBeInTheDocument();
    });

    expect(screen.queryByTestId('tool-activity-panel')).not.toBeInTheDocument();
    expect(screen.queryByText('State: CONFLICT_REQUIRES_REVIEW')).not.toBeInTheDocument();
    expect(screen.queryByText('CONFLICT_REQUIRES_REVIEW')).not.toBeInTheDocument();
    expect(screen.queryByText('Request Checks')).not.toBeInTheDocument();
    expect(screen.queryByText('Agent Activity Logs')).not.toBeInTheDocument();
    expect(screen.queryByText('Order eligibility verified')).not.toBeInTheDocument();
    expect(screen.queryByTestId('citations-container')).not.toBeInTheDocument();
  });
});
