import React from 'react';
import type { UserContext, UserRole } from '../types';

interface ContextSwitcherProps {
  currentContext: UserContext;
  onContextChange: (context: UserContext) => void;
}

interface DemoOption {
  label: string;
  role: UserRole;
  accountId?: string;
  userId: string;
}

const DEMO_OPTIONS: DemoOption[] = [
  {
    label: 'Northstar Customer',
    role: 'CUSTOMER',
    accountId: 'ACCT-001',
    userId: 'customer-demo',
  },
  {
    label: 'LumenWorks Customer',
    role: 'CUSTOMER',
    accountId: 'ACCT-002',
    userId: 'ACCT-002',
  },
  {
    label: 'Support Agent',
    role: 'SUPPORT_AGENT',
    userId: 'support-demo',
  },
  {
    label: 'Operations Admin',
    role: 'OPERATIONS_ADMIN',
    userId: 'ops-demo',
  },
];

export const ContextSwitcher: React.FC<ContextSwitcherProps> = ({
  currentContext,
  onContextChange,
}) => {
  return (
    <div className="context-switcher" data-testid="context-switcher">
      <h3 className="panel-title">User Context Selector</h3>
      <div className="switcher-options">
        {DEMO_OPTIONS.map((opt) => {
          const isSelected =
            currentContext.role === opt.role &&
            currentContext.user_id === opt.userId &&
            currentContext.customer_account_id === opt.accountId;

          return (
            <label
              key={opt.userId}
              className={`switcher-option-label ${isSelected ? 'selected' : ''}`}
            >
              <input
                type="radio"
                name="context"
                checked={isSelected}
                aria-label={opt.label}
                onChange={() =>
                  onContextChange({
                    role: opt.role,
                    customer_account_id: opt.accountId,
                    user_id: opt.userId,
                  })
                }
                className="switcher-radio-input"
              />
              <span className="switcher-option-text">
                <span className="option-name">{opt.label}</span>
                <span className="option-meta">
                  Role: {opt.role}
                  {opt.accountId ? ` | Account: ${opt.accountId}` : ''}
                </span>
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
};
