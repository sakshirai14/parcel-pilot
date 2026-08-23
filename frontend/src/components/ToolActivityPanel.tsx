import React from 'react';
import { CheckCircle2, XCircle, Play } from 'lucide-react';
import type { ToolActivity } from '../types';

interface ToolActivityPanelProps {
  activities: ToolActivity[];
  role?: string;
}

export const ToolActivityPanel: React.FC<ToolActivityPanelProps> = ({ activities, role }) => {
  if (!activities || activities.length === 0) return null;

  const isCustomer = role === 'CUSTOMER';

  return (
    <div className="tool-activity-panel" data-testid="tool-activity-panel">
      <div className="activity-header">
        <span className="activity-title">
          {isCustomer ? 'Request Checks' : 'Agent Activity Logs'}
        </span>
      </div>
      <ul className="activity-list">
        {activities.map((act, index) => {
          const isCompleted = act.status === 'COMPLETED';
          const isFailed = act.status === 'FAILED';

          return (
            <li key={`${act.tool}-${index}`} className="activity-item">
              {isCompleted && <CheckCircle2 size={14} className="icon-success" />}
              {isFailed && <XCircle size={14} className="icon-error" />}
              {!isCompleted && !isFailed && <Play size={14} className="icon-running" />}
              <span className="activity-tool-name">
                {isCustomer ? mapCustomerFriendlyName(act.tool) : formatToolName(act.tool)}
              </span>
              <span className={`activity-status-badge ${act.status.toLowerCase()}`}>
                {act.status}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

function mapCustomerFriendlyName(toolName: string): string {
  const name = toolName.toLowerCase();
  if (name === 'lookup_operational_data') {
    return 'Order eligibility verified';
  }
  if (name === 'search_documents') {
    return 'Cancellation eligibility verified';
  }
  if (name === 'calculate_entitlement') {
    return 'Fee eligibility calculated';
  }
  if (name === 'calculate_sla') {
    return 'SLA response targets checked';
  }
  if (name === 'prepare_action') {
    return 'Action requirements validated';
  }
  return formatToolName(toolName);
}

function formatToolName(name: string): string {
  return name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
