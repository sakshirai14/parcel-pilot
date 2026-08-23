import React, { useState } from 'react';
import { ShieldAlert, CheckCircle, XCircle } from 'lucide-react';
import type { ActionProposal, UserContext } from '../types';
import { confirmAction, cancelAction } from '../services/api';

interface ConfirmationCardProps {
  proposal: ActionProposal;
  userContext: UserContext;
  onActionCompleted: (resultMessage: string, isSuccess: boolean) => void;
}

export const ConfirmationCard: React.FC<ConfirmationCardProps> = ({
  proposal,
  userContext,
  onActionCompleted,
}) => {
  const [status, setStatus] = useState<'PENDING' | 'EXECUTING' | 'CANCELLING' | 'SUCCESS' | 'ERROR'>('PENDING');
  const [message, setMessage] = useState<string>('');
  const [execId, setExecId] = useState<string>('');

  const handleConfirm = async () => {
    setStatus('EXECUTING');
    try {
      const res = await confirmAction(proposal.action_id, userContext.user_id || 'system-agent', proposal.proposed_changes);
      if (res.status === 'EXECUTED' || res.status === 'ALREADY_EXECUTED') {
        setStatus('SUCCESS');
        setMessage(res.message || 'Action executed successfully.');
        setExecId(res.action_id || proposal.action_id);
        onActionCompleted(res.message || 'Action executed successfully.', true);
      } else {
        setStatus('ERROR');
        setMessage(res.message || 'Execution failed.');
        onActionCompleted(res.message || 'Execution failed.', false);
      }
    } catch (err: any) {
      setStatus('ERROR');
      setMessage(err.message || 'An error occurred during execution.');
      onActionCompleted(err.message || 'An error occurred during execution.', false);
    }
  };

  const handleCancel = async () => {
    setStatus('CANCELLING');
    try {
      await cancelAction(proposal.action_id, userContext.user_id || 'system-agent');
      setStatus('SUCCESS');
      setMessage('Action cancelled.');
      onActionCompleted('Action cancelled.', false);
    } catch (err: any) {
      // Even if endpoint fails, we show local cancellation
      setStatus('SUCCESS');
      setMessage('Action cancelled.');
      onActionCompleted('Action cancelled.', false);
    }
  };

  const isButtonsDisabled = status === 'EXECUTING' || status === 'CANCELLING' || status === 'SUCCESS';

  return (
    <div className="confirmation-card" data-testid="confirmation-card">
      <div className="card-header">
        <ShieldAlert size={16} className="header-icon" />
        <span className="header-text">Action Requires Confirmation</span>
      </div>

      <div className="card-body">
        <h4 className="proposal-title">{proposal.summary}</h4>
        
        <div className="proposal-details">
          <div className="detail-row">
            <span className="detail-label">Action ID:</span>
            <span className="detail-value font-mono">{proposal.action_id}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Action Type:</span>
            <span className="detail-value">{proposal.action_type}</span>
          </div>
          {proposal.ticket_id && (
            <div className="detail-row">
              <span className="detail-label">Ticket Reference:</span>
              <span className="detail-value">{proposal.ticket_id}</span>
            </div>
          )}
          {proposal.proposed_changes && (
            <div className="proposed-changes-box">
              <span className="box-title">Proposed Details:</span>
              <pre className="changes-pre">
                {JSON.stringify(proposal.proposed_changes, null, 2)}
              </pre>
            </div>
          )}
        </div>

        {status === 'PENDING' && (
          <div className="card-actions">
            <button
              onClick={handleConfirm}
              disabled={isButtonsDisabled}
              className="confirm-btn"
              data-testid="confirm-btn"
            >
              Confirm
            </button>
            <button
              onClick={handleCancel}
              disabled={isButtonsDisabled}
              className="cancel-btn"
              data-testid="cancel-btn"
            >
              Cancel
            </button>
          </div>
        )}

        {status === 'EXECUTING' && <div className="card-loader-text">Executing Action...</div>}
        {status === 'CANCELLING' && <div className="card-loader-text">Cancelling Action...</div>}

        {status === 'SUCCESS' && (
          <div className="action-result success" data-testid="action-success">
            <CheckCircle size={16} />
            <span className="result-text">{message}</span>
            {execId && <span className="result-subtext font-mono">Action ID: {execId}</span>}
          </div>
        )}

        {status === 'ERROR' && (
          <div className="action-result error" data-testid="action-error">
            <XCircle size={16} />
            <span className="result-text">{message}</span>
          </div>
        )}
      </div>
    </div>
  );
};
